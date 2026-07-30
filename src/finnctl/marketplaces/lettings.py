"""Lettings (property to let / homes for rent) client for finn.no.

Searches https://www.finn.no/realestate/lettings/search.html and parses the
result cards from the returned HTML. Structurally close to the homes-for-sale
search, but rentals have no ownership form, the price is a monthly rent, and
the sort keys use ``RENT_*`` instead of ``PRICE_*``.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from ..client import BASE_URL, FinnClient
from .realestate import (
    MAX_BEDROOMS_FILTER,
    _extract_total,
    _to_int,
    resolve_location_code,
)

SEARCH_PATH = "/realestate/lettings/search.html"

# Sort values accepted by finn.no's lettings search (raw API values).
# Note: rentals sort on RENT_*, not PRICE_*.
SORT_MAP: dict[str, str] = {
    "newest":     "PUBLISHED_DESC",
    "price-asc":  "RENT_ASC",
    "price-desc": "RENT_DESC",
    "area-asc":   "AREA_ASC",
    "area-desc":  "AREA_DESC",
    "relevance":  "RELEVANCE",
}

# Friendly property-type names -> finn.no `property_type` codes.
# Codes verified empirically against the live lettings search.
PROPERTY_TYPES: dict[str, int] = {
    "enebolig":         1,
    "hus":              1,   # alias for enebolig
    "tomannsbolig":     2,
    "leilighet":        3,
    "rekkehus":         4,
    "garasje":          6,
    "hytte":            12,
    "hybel":            16,
    "bofellesskap":     17,  # "Rom i bofellesskap"
    "andre":            18,
}

# Canonical property-type labels as shown on the cards (for parsing the type
# out of a plain span like "Leilighet" that carries no bedroom count).
_TYPE_LABELS = {
    "Enebolig", "Tomannsbolig", "Leilighet", "Rekkehus", "Garasje/Parkering",
    "Hytte", "Hybel", "Rom i bofellesskap", "Andre",
}


@dataclass
class RentalAd:
    """A single home-for-rent listing."""

    id: str
    title: str
    url: str
    rent: int | None = None           # Monthly rent (NOK)
    currency: str = "NOK"
    location: str | None = None
    area_m2: int | None = None        # Primary living area (m²)
    bedrooms: int | None = None
    property_type: str | None = None
    image_url: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RentalSearchResult:
    ads: list[RentalAd] = field(default_factory=list)
    total: int = 0
    page: int = 1

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "page": self.page,
            "ads": [a.to_dict() for a in self.ads],
        }


class LettingsClient:
    """Client for finn.no lettings (homes to rent)."""

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
        area_min: int | None = None,
        location: str | None = None,
    ) -> RentalSearchResult:
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
            params["location"] = resolve_location_code(location)

        if property_types:
            params["property_type"] = [resolve_property_type(t) for t in property_types]

        soup = self._finn.get_page(SEARCH_PATH, params=params)

        ads: list[RentalAd] = []
        seen: set[str] = set()  # the top "featured" card duplicates a real listing
        for card in soup.find_all("article", class_=re.compile(r"sf-search-ad")):
            ad = _parse_card(card)
            if ad is not None and ad.id not in seen:
                seen.add(ad.id)
                ads.append(ad)

        return RentalSearchResult(ads=ads, total=_extract_total(soup), page=page)


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


def _parse_card(card) -> RentalAd | None:
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

    area_m2 = rent = bedrooms = None
    property_type = None
    for span in card.find_all("span"):
        text = span.get_text(" ", strip=True)
        if not text:
            continue
        if text.endswith("m²") and area_m2 is None:
            area_m2 = _to_int(text)
        elif text.endswith("kr") and rent is None:
            rent = _to_int(text)
        elif "∙" in text and "soverom" in text and property_type is None:
            # Type + bedrooms line, e.g. "Leilighet ∙ 1 soverom".
            parts = [p.strip() for p in text.split("∙")]
            property_type = parts[0]
            bd = re.search(r"(\d+)", parts[-1])
            bedrooms = int(bd.group(1)) if bd else None
        elif text in _TYPE_LABELS and property_type is None:
            # Type-only line (no bedroom count), e.g. "Leilighet".
            property_type = text

    img = card.find("img")
    image_url = img.get("src") if img else None

    return RentalAd(
        id=finnkode,
        title=title,
        url=url,
        rent=rent,
        location=location,
        area_m2=area_m2,
        bedrooms=bedrooms,
        property_type=property_type,
        image_url=image_url,
    )
