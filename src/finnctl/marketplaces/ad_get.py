"""
Fetches full ad data from finn.no for caching.

Source: the edit page at /recommerce/create/<finn_id> embeds the complete
ad payload (in API-ready format) as a JSON script tag. This is the same
format accepted by the PUT /recommerce/create/api/item/<id> endpoint.
"""

from __future__ import annotations

import json
import re

from ..auth import Session
from ..client import FinnClient


EDIT_BASE = "/recommerce/create"


def fetch_ad_payload(finn: FinnClient, session: Session, finn_id: str) -> dict:
    """
    Fetch the full ad edit payload from finn.no's recommerce create page.

    Returns a dict with keys: data (title, address, image, description,
    trade_type, price, category, condition), model, etag, state, violations.

    Raises ValueError if the ad cannot be fetched or parsed.
    """
    resp = finn._http.get(
        f"{EDIT_BASE}/{finn_id}",
        headers=session.auth_header(),
    )
    resp.raise_for_status()
    return _extract_payload(resp.text, finn_id)


def _extract_payload(html: str, finn_id: str) -> dict:
    """Find and parse the embedded JSON ad payload in the edit page HTML."""
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    for script in scripts:
        s = script.strip()
        if not s.startswith("{"):
            continue
        try:
            data = json.loads(s)
        except json.JSONDecodeError:
            continue
        if "data" in data and "model" in data and "etag" in data:
            return data
    raise ValueError(
        f"Could not extract ad payload for {finn_id}. "
        "The ad may not belong to you, or may not be editable."
    )


def image_uris(payload: dict) -> list[str]:
    """Return the list of image URIs from an ad payload."""
    return [img["uri"] for img in payload.get("data", {}).get("image", [])]


def marketplace_from_payload(payload: dict) -> str:
    model = payload.get("model", "recommerce")
    return {"recommerce": "torget", "car": "bil", "realestate": "eiendom"}.get(model, model)
