"""
Pushes a cached ad payload back to finn.no via the edit API.

Endpoint: PUT /recommerce/create/api/item/<finn_id>
Headers:  Content-Type: application/json, E-Tag: <etag>
Body:     the ad payload dict (same format returned by ad_get.fetch_ad_payload)

This updates the existing ad (title, description, price, images, etc.) and
leaves it in an inactive/draft state — the user must visit the edit URL in
their browser to review and publish.

NOTE: Creating a *brand-new* copy of an ad requires additional API discovery
(HAR capture from the browser create flow). This module will be extended once
that endpoint is known.
"""

from __future__ import annotations

import copy
import json
import re

from ..auth import Session
from ..client import FinnClient


EDIT_BASE = "/recommerce/create"


def push_ad(
    finn: FinnClient,
    session: Session,
    finn_id: str,
    payload: dict,
    *,
    price: int | None = None,
) -> str:
    """
    PUT the cached ad payload to finn.no.

    Args:
        finn_id:  The finn ad ID to update.
        payload:  The ad payload dict (from ad_get or ad_cache).
        price:    If given, override the price (NOK) in the payload.

    Returns:
        The edit URL the user should visit to review and publish.

    Raises:
        httpx.HTTPStatusError on API failures.
    """
    payload = copy.deepcopy(payload)

    if price is not None:
        payload.setdefault("data", {}).setdefault("price", {})["price_amount"] = price

    etag = payload.get("etag", "")

    resp = finn._http.put(
        f"{EDIT_BASE}/api/item/{finn_id}",
        headers={
            **session.auth_header(),
            "Content-Type": "application/json",
            "E-Tag": etag,
        },
        json=payload,
    )
    resp.raise_for_status()

    return f"https://www.finn.no{EDIT_BASE}/{finn_id}"


def _fetch_csrf_token(finn: FinnClient, session: Session) -> str:
    """
    Fetch the CSRF token from window.MYADS_STATE on the /my-items page.

    Raises ValueError if the token cannot be found.
    """
    resp = finn._http.get("/my-items", headers=session.auth_header())
    resp.raise_for_status()
    m = re.search(r'window\.MYADS_STATE\s*=\s*(\{)', resp.text)
    if not m:
        raise ValueError("Could not find MYADS_STATE on /my-items page")
    start = m.start(1)
    depth = 0
    in_string = False
    escape = False
    for i, ch in enumerate(resp.text[start:], start):
        if escape:
            escape = False
        elif ch == '\\' and in_string:
            escape = True
        elif ch == '"':
            in_string = not in_string
        elif not in_string:
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    state = json.loads(resp.text[start:i + 1])
                    break
    else:
        raise ValueError("Could not parse MYADS_STATE JSON")

    token = state.get("csrfToken")
    if not token:
        raise ValueError("csrfToken not found in MYADS_STATE")
    return token


def pause_ad(finn: FinnClient, session: Session, finn_id: str) -> None:
    """
    Hide (pause) a currently active ad from search results.

    Uses the internal /my-items/api/action endpoint with the CSRF token
    extracted from window.MYADS_STATE. The action path comes from the
    ad's PAUSE action in the summary API (/items/<id>/pause).

    Raises httpx.HTTPStatusError on API failures, ValueError if CSRF not found.
    """
    csrf = _fetch_csrf_token(finn, session)
    resp = finn._http.put(
        f"/my-items/api/action/items/{finn_id}/pause",
        headers={
            **session.auth_header(),
            "CSRF-Token": csrf,
        },
    )
    resp.raise_for_status()
