"""Realestate (Bolig til salgs / homes for sale) client for finn.no.

Searches https://www.finn.no/realestate/homes/search.html and parses the
result cards from the returned HTML. Unlike Torget, the homes search page
does not embed a schema.org CollectionPage, so results are read directly
from the ``<article class="sf-search-ad">`` cards.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from ..client import BASE_URL, FinnClient

SEARCH_PATH = "/realestate/homes/search.html"

# finn.no's "Antall soverom" facet offers 1–5, where 5 means "5 or more".
MAX_BEDROOMS_FILTER = 5

# Sort values accepted by finn.no's homes search (raw API values).
SORT_MAP: dict[str, str] = {
    "newest":     "PUBLISHED_DESC",
    "oldest":     "PUBLISHED_ASC",
    "price-asc":  "PRICE_ASC",
    "price-desc": "PRICE_DESC",
    "area-asc":   "AREA_ASC",
    "area-desc":  "AREA_DESC",
}

# Friendly property-type names -> finn.no `property_type` codes.
# Codes verified empirically against the live homes search.
PROPERTY_TYPES: dict[str, int] = {
    "enebolig":      1,
    "hus":           1,   # alias for enebolig
    "tomannsbolig":  2,
    "leilighet":     3,
    "rekkehus":      4,
    "garasje":       6,
}

# Friendly ownership-form names -> finn.no `ownership_type` codes.
OWNERSHIP_TYPES: dict[str, int] = {
    "obligasjon": 1,
    "aksje":      2,
    "selveier":   3,
    "eier":       3,   # alias
    "borettslag": 4,
    "andel":      4,   # alias
}


@dataclass
class HomeAd:
    """A single home-for-sale listing."""

    id: str
    title: str
    url: str
    price: int | None = None          # Prisantydning (asking price, NOK)
    total_price: int | None = None    # Totalpris (incl. fees, NOK)
    currency: str = "NOK"
    location: str | None = None
    area_m2: int | None = None        # Primary living area (m²)
    bedrooms: int | None = None
    property_type: str | None = None
    ownership: str | None = None
    image_url: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HomeSearchResult:
    ads: list[HomeAd] = field(default_factory=list)
    total: int = 0
    page: int = 1

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "page": self.page,
            "ads": [a.to_dict() for a in self.ads],
        }


# A single Norwegian-formatted number, e.g. "5 640 000" (space/nbsp/thin-space
# grouped). Matches only the FIRST number so price ranges on new-development
# listings ("5 640 000 - 6 050 000 kr") yield the lower ("from") price.
_NUMBER_RE = re.compile(r"\d[\d\s  ]*\d|\d")


def _to_int(text: str | None) -> int | None:
    """Extract the first integer from a Norwegian-formatted number string."""
    if not text:
        return None
    m = _NUMBER_RE.search(text)
    if not m:
        return None
    return int(re.sub(r"\D", "", m.group()))


class RealestateClient:
    """Client for finn.no 'Bolig til salgs' (homes for sale)."""

    def __init__(self, finn: FinnClient) -> None:
        self._finn = finn

    def search(
        self,
        query: str | None = None,
        *,
        page: int = 1,
        sort: str = "newest",
        price_min: int | None = None,
        price_max: int | None = None,
        property_types: list[str] | None = None,
        bedrooms_min: int | None = None,
        ownership_types: list[str] | None = None,
        area_min: int | None = None,
        location: str | None = None,
    ) -> HomeSearchResult:
        params: dict = {"sort": SORT_MAP.get(sort, sort)}
        if query:
            params["q"] = query
        if page > 1:
            params["page"] = page
        if price_min is not None:
            params["price_from"] = price_min
        if price_max is not None:
            params["price_to"] = price_max
        if bedrooms_min is not None:
            # finn.no's bedroom facet tops out at "5+"; higher values are
            # silently ignored by the server, so clamp to keep the filter active.
            params["min_bedrooms"] = min(bedrooms_min, MAX_BEDROOMS_FILTER)
        if area_min is not None:
            params["area_from"] = area_min
        if location:
            params["location"] = self._resolve_location(location)

        if property_types:
            params["property_type"] = [resolve_property_type(t) for t in property_types]
        if ownership_types:
            params["ownership_type"] = [resolve_ownership_type(t) for t in ownership_types]

        soup = self._finn.get_page(SEARCH_PATH, params=params)

        ads: list[HomeAd] = []
        seen: set[str] = set()  # the top "featured" card duplicates a real listing
        for card in soup.find_all("article", class_=re.compile(r"sf-search-ad")):
            ad = _parse_card(card)
            if ad is not None and ad.id not in seen:
                seen.add(ad.id)
                ads.append(ad)

        return HomeSearchResult(ads=ads, total=_extract_total(soup), page=page)

    @staticmethod
    def _resolve_location(location: str) -> str:
        """Accept a raw finn.no location code as-is, or map a known Norwegian
        county name to its code.

        Location codes are hierarchical, and the leading digit is the depth:
        ``0.`` = fylke (county), ``1.`` = kommune, ``2.`` = bydel/område.
        E.g. ``0.20007`` = Buskerud, ``2.20007.20110.23007`` = Buskerud >
        Drammen > Nedre Eiker. County-level codes are the same ``0.20xxx``
        values used elsewhere in finnctl."""
        loc = location.strip()
        if re.fullmatch(r"\d+(\.\d+)*", loc):
            return loc
        from ..client import LOCATION_CODES
        return LOCATION_CODES.get(loc.lower(), loc)  # pass unknown through


def resolve_property_type(name: str) -> int:
    """Map a friendly name or numeric code to a finn.no property_type code."""
    key = name.strip().lower()
    if key in PROPERTY_TYPES:
        return PROPERTY_TYPES[key]
    if key.isdigit():
        return int(key)
    raise ValueError(
        f"Unknown property type {name!r}. "
        f"Valid: {', '.join(sorted(set(PROPERTY_TYPES)))}"
    )


def resolve_ownership_type(name: str) -> int:
    """Map a friendly name or numeric code to a finn.no ownership_type code."""
    key = name.strip().lower()
    if key in OWNERSHIP_TYPES:
        return OWNERSHIP_TYPES[key]
    if key.isdigit():
        return int(key)
    raise ValueError(
        f"Unknown ownership form {name!r}. "
        f"Valid: {', '.join(sorted(set(OWNERSHIP_TYPES)))}"
    )


def _extract_total(soup) -> int:
    """Extract the total result count from the page.

    The unfiltered page reads 'N boliger'; a filtered search reads 'N treff'.
    """
    text = soup.get_text(" ", strip=True)
    m = re.search(r"(\d[\d\s]*?)\s*(?:boliger|treff)\b", text)
    return (_to_int(m.group(1)) or 0) if m else 0


def _parse_card(card) -> HomeAd | None:
    link = card.find("a", class_=re.compile(r"sf-search-ad-link"))
    if link is None:
        return None

    href = link.get("href", "")
    m = re.search(r"finnkode=(\d+)", href)
    finnkode = link.get("id") or (m.group(1) if m else None)
    if not finnkode:
        return None

    url = href if href.startswith("http") else f"{BASE_URL}{href}"

    heading = card.find("h2", class_=re.compile(r"sf-realestate-heading"))
    title = heading.get_text(" ", strip=True) if heading else link.get_text(" ", strip=True)

    loc_div = card.find("div", class_=re.compile(r"sf-realestate-location"))
    location = loc_div.get_text(" ", strip=True) if loc_div else None

    area_m2 = price = total_price = None
    ownership = property_type = bedrooms = None
    for span in card.find_all("span"):
        text = span.get_text(" ", strip=True)
        if not text:
            continue
        if text.endswith("m²") and area_m2 is None:
            area_m2 = _to_int(text)
        elif text.startswith("Totalpris"):
            total_price = _to_int(text)
        elif text.endswith("kr") and price is None:
            price = _to_int(text)
        elif "∙" in text and "kr" not in text and ownership is None:
            # Metadata line: "Selveier ∙ Enebolig ∙ 3 soverom"
            # (project listings omit bedrooms: "Selveier ∙ Enebolig").
            parts = [p.strip() for p in text.split("∙") if p.strip()]
            if len(parts) >= 2:
                ownership, property_type = parts[0], parts[1]
                if len(parts) >= 3:
                    bd = re.search(r"(\d+)", parts[2])
                    bedrooms = int(bd.group(1)) if bd else None

    img = card.find("img")
    image_url = img.get("src") if img else None

    return HomeAd(
        id=finnkode,
        title=title,
        url=url,
        price=price,
        total_price=total_price,
        location=location,
        area_m2=area_m2,
        bedrooms=bedrooms,
        property_type=property_type,
        ownership=ownership,
        image_url=image_url,
    )
