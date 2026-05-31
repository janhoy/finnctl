"""Generic finn.no HTTP client — handles all low-level HTTP traffic."""

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx
from bs4 import BeautifulSoup


BASE_URL = "https://www.finn.no"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8",
}


@dataclass
class SearchAd:
    id: str
    title: str
    url: str
    price: int | None = None
    currency: str = "NOK"
    location: str | None = None
    condition: str | None = None
    image_url: str | None = None


@dataclass
class SearchResult:
    ads: list[SearchAd] = field(default_factory=list)
    total: int = 0
    page: int = 1


class FinnClient:
    """
    Generic client for finn.no. Fetches pages and parses common structures.
    Specific marketplaces subclass or compose this to add their own logic.
    """

    def __init__(self, timeout: float = 15.0) -> None:
        self._http = httpx.Client(
            base_url=BASE_URL,
            headers=HEADERS,
            follow_redirects=True,
            timeout=timeout,
        )

    def get_page(self, path: str, params: dict[str, Any] | None = None) -> BeautifulSoup:
        response = self._http.get(path, params=params)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    def extract_schema_items(self, soup: BeautifulSoup) -> list[dict]:
        """Extract itemListElement entries from schema.org CollectionPage JSON-LD."""
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string)
                if data.get("@type") == "CollectionPage":
                    entity = data.get("mainEntity", {})
                    return entity.get("itemListElement", [])
            except (json.JSONDecodeError, AttributeError):
                continue
        return []

    def extract_total(self, soup: BeautifulSoup) -> int:
        """Try to extract total result count from schema.org description."""
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string)
                if data.get("@type") == "CollectionPage":
                    desc = data.get("description", "")
                    m = re.search(r"(\d+)\s+annonse", desc)
                    if m:
                        return int(m.group(1))
            except (json.JSONDecodeError, AttributeError):
                continue
        return 0

    def extract_card_locations(self, soup: BeautifulSoup) -> list[str | None]:
        """
        Extract location strings from ad cards in the same order as the page.
        Location is in <span class="whitespace-nowrap truncate mr-8">.
        """
        locations: list[str | None] = []
        for card in soup.find_all("article", class_=re.compile(r"sf-search-ad")):
            span = card.find("span", class_=lambda c: c and "truncate" in c and "mr-8" in c)
            location = span.get_text(strip=True) if span else None
            locations.append(location or None)
        return locations

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
