"""
Client for fetching the current user's own ads from finn.no.

Uses the internal /my-items/api/summary JSON endpoint that the
finn.no My Ads SPA calls. Requires an authenticated session (cookie).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..auth import Session
from ..client import FinnClient


MY_ITEMS_API = "/my-items/api/summary"

# Maps human-readable CLI state names → finn.no API facet values.
STATE_MAP: dict[str, str] = {
    "active":   "ACTIVE",
    "aktiv":    "ACTIVE",
    "all":      "ALL",
    "alle":     "ALL",
    "rejected": "REJECTED",
    "avvist":   "REJECTED",
    "expired":  "EXPIRED",
    "utløpt":   "EXPIRED",
    "done":     "DISPOSED",
    "ferdig":   "DISPOSED",
}

# Maps finn.no vertical identifiers → short marketplace names.
_VERTICAL_MAP = {
    "RECOMMERCE":        "torget",
    "CAR_SALE":          "bil",
    "REALESTATE_HOMES":  "eiendom",
    "REALESTATE_LETTING":"bolig-leie",
    "BOAT_SALE":         "båt",
    "MC_SALE":           "mc",
    "JOB":               "jobb",
}


@dataclass
class MyAd:
    finn_id: str          # e.g. "446966445"
    title: str
    url: str              # full https://www.finn.no/... URL
    marketplace: str      # e.g. "torget", "bil"
    status: str | None = None   # e.g. "Solgt", "Avvist", "Utløpt"
    price: int | None = None
    image_url: str | None = None
    updated: str | None = None  # ISO-8601 date string, e.g. "2026-05-07T01:11:14+02:00"


@dataclass
class MyAdsResult:
    ads: list[MyAd] = field(default_factory=list)
    total: int = 0
    facets: dict[str, int] = field(default_factory=dict)  # facet name → count


class MyItemsClient:
    """Fetches the user's own ads from finn.no's internal my-items API."""

    BASE_URL = "https://www.finn.no"

    def __init__(self, finn: FinnClient, session: Session) -> None:
        self._finn = finn
        self._session = session

    PAGE_SIZE = 50  # finn.no API maximum page size

    def fetch_all(
        self,
        marketplace: str | None = None,
        state: str = "active",
    ) -> MyAdsResult:
        """
        Return all of the user's ads, paginating through the API automatically.

        Args:
            marketplace: optional marketplace filter (e.g. "torget", "bil").
            state: one of active | all | rejected | expired | done.
        """
        facet = STATE_MAP.get(state, "ACTIVE")

        all_summaries: list[dict] = []
        facets: dict[str, int] = {}
        total = 0
        offset = 0

        while True:
            resp = self._finn._http.get(
                MY_ITEMS_API,
                headers=self._session.auth_header(),
                params={"limit": self.PAGE_SIZE, "offset": offset, "facet": facet},
            )
            resp.raise_for_status()
            data = resp.json()

            if not facets:
                facets = {f["name"]: f["total"] for f in data.get("facets", [])}
                total = data.get("total", 0)

            page = data.get("summaries", [])
            all_summaries.extend(page)

            if len(all_summaries) >= total or len(page) < self.PAGE_SIZE:
                break
            offset += self.PAGE_SIZE

        ads = [self._parse_summary(s) for s in all_summaries]

        if marketplace:
            mp = marketplace.lower()
            ads = [a for a in ads if a.marketplace.lower() == mp]

        return MyAdsResult(ads=ads, total=total, facets=facets)

    # ── parsing ───────────────────────────────────────────────────────────────

    def _parse_summary(self, s: dict) -> MyAd:
        finn_id = str(s.get("id", ""))

        # Resolve URL from actions or fall back to bare ID path
        url = self.BASE_URL + f"/{finn_id}"
        for action in s.get("actions", []):
            if action.get("name") == "OBJECT_PAGE":
                url = self.BASE_URL + action["url"]
                break

        vertical = s.get("vertical", "")
        marketplace = _VERTICAL_MAP.get(vertical, vertical.lower() or "ukjent")

        ad_data = s.get("data", {})
        title = ad_data.get("title", "")
        subtitle = ad_data.get("subtitle", "")
        price = _parse_price(subtitle)

        image_path = ad_data.get("image")
        image_url = f"https://images.finncdn.no/dynamic/480x360c/{image_path}" if image_path else None

        state = s.get("state", {})
        status = state.get("label")  # e.g. "Solgt", "Avvist", "Utløpt"
        updated = s.get("updated")   # ISO-8601 string

        return MyAd(
            finn_id=finn_id,
            title=title,
            url=url,
            marketplace=marketplace,
            status=status,
            price=price,
            image_url=image_url,
            updated=updated,
        )


def fetch_ad_state(finn: FinnClient, session: Session, finn_id: str) -> str:
    """
    Return the current state type of an ad (e.g. 'ACTIVE', 'EXPIRED').

    Calls /my-items/api/single?adId=<id>. Raises ValueError if not found.
    """
    resp = finn._http.get(
        "/my-items/api/single",
        headers=session.auth_header(),
        params={"adId": finn_id},
    )
    resp.raise_for_status()
    data = resp.json()
    state_type = data.get("state", {}).get("type")
    if not state_type:
        raise ValueError(f"Could not determine state for ad {finn_id}")
    return state_type


def _parse_price(subtitle: str) -> int | None:
    """Extract price from subtitle strings like 'Torget til salgs 2 500,−'."""
    m = re.search(r"([\d\s]+)[,.]?[−\-]?\s*kr|kr\s*([\d\s]+)", subtitle)
    if not m:
        m = re.search(r"(\d[\d\s]*\d|\d)\s*[,.]?[−\-]", subtitle)
    if m:
        raw = (m.group(1) or m.group(2) or "").replace("\u202f", "").replace("\xa0", "").replace(" ", "")
        try:
            return int(raw)
        except ValueError:
            pass
    return None
