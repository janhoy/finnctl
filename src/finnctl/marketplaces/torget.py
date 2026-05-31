"""Torget (general marketplace) client for finn.no."""

from ..client import FinnClient, SearchAd, SearchResult


SEARCH_PATH = "/recommerce/forsale/search"

CONDITION_MAP = {
    "https://schema.org/NewCondition": "Ny",
    "https://schema.org/UsedCondition": "Brukt",
    "https://schema.org/RefurbishedCondition": "Renovert",
    "https://schema.org/DamagedCondition": "Skadet",
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
        sort: str = "PUBLISHED_DESC",
    ) -> SearchResult:
        params: dict = {"q": query, "sort": sort}
        if page > 1:
            params["page"] = page

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

            location = locations[i] if i < len(locations) else None

            ads.append(
                SearchAd(
                    id=ad_id,
                    title=product.get("name", ""),
                    url=url,
                    price=price,
                    currency=offer.get("priceCurrency", "NOK"),
                    location=location,
                    condition=condition,
                    image_url=product.get("image"),
                )
            )

        return SearchResult(ads=ads, total=total, page=page)
