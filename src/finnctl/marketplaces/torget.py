"""Torget (general marketplace) client for finn.no."""

from ..client import Coordinates, FinnClient, SearchAd, SearchResult


SEARCH_PATH = "/recommerce/forsale/search"

# Map user-friendly sort names to finn.no API values.
# finn.no supports: PUBLISHED_DESC, PUBLISHED_ASC, RELEVANCE, CLOSEST, PRICE_DESC, PRICE_ASC
SORT_MAP: dict[str, str] = {
    "newest":     "PUBLISHED_DESC",
    "oldest":     "PUBLISHED_ASC",
    "relevance":  "RELEVANCE",
    "price-asc":  "PRICE_ASC",
    "price-desc": "PRICE_DESC",
    "distance":   "CLOSEST",
}

CONDITION_MAP = {
    "https://schema.org/NewCondition":        "Ny",
    "https://schema.org/UsedCondition":       "Brukt",
    "https://schema.org/RefurbishedCondition": "Renovert",
    "https://schema.org/DamagedCondition":    "Skadet",
}


class TorgetClient:
    """
    Client for finn.no Torget (second-hand general marketplace).
    Uses FinnClient for HTTP and HTML parsing.
    """

    def __init__(self, finn: FinnClient) -> None:
        self._finn = finn

    def search(
        self,
        query: str,
        *,
        page: int = 1,
        sort: str = "newest",
        price_min: int | None = None,
        price_max: int | None = None,
        location: str | None = None,
        coords: Coordinates | None = None,
    ) -> SearchResult:
        finn_sort = SORT_MAP.get(sort, sort)  # allow raw finn.no values as fallback

        params: dict = {"q": query, "sort": finn_sort}
        if page > 1:
            params["page"] = page
        if price_min is not None:
            params["price_from"] = price_min
        if price_max is not None:
            params["price_to"] = price_max

        # Location: area code for geographic filtering; coordinates for CLOSEST sort
        if location:
            finn_code, geocoded = self._finn.resolve_location(location)
            if finn_code:
                params["location"] = finn_code
            if geocoded:
                if finn_code:
                    # Area code found — use geocoded coords to anchor the CLOSEST sort
                    # (only meaningful when sort=CLOSEST; otherwise ignored by finn.no)
                    if finn_sort == "CLOSEST":
                        coords = geocoded
                else:
                    # No area code — fall back to distance sort from that city's coordinates
                    coords = geocoded
                    if finn_sort != "CLOSEST":
                        params["sort"] = "CLOSEST"

        if coords:
            params["lat"] = round(coords.lat, 6)
            params["lon"] = round(coords.lon, 6)

        soup = self._finn.get_page(SEARCH_PATH, params=params)

        schema_items = self._finn.extract_schema_items(soup)
        locations = self._finn.extract_card_locations(soup)
        total = self._finn.extract_total(soup)

        ads: list[SearchAd] = []
        for i, entry in enumerate(schema_items):
            product = entry.get("item", {})
            offer = product.get("offers", {})

            url = product.get("url", "")
            ad_id = url.rstrip("/").split("/")[-1] if url else str(i)

            price_str = offer.get("price")
            price = int(float(price_str)) if price_str else None

            condition_uri = product.get("itemCondition")
            condition = CONDITION_MAP.get(condition_uri) if condition_uri else None

            loc = locations[i] if i < len(locations) else None

            ads.append(
                SearchAd(
                    id=ad_id,
                    title=product.get("name", ""),
                    url=url,
                    price=price,
                    currency=offer.get("priceCurrency", "NOK"),
                    location=loc,
                    condition=condition,
                    image_url=product.get("image"),
                )
            )

        return SearchResult(ads=ads, total=total, page=page)
