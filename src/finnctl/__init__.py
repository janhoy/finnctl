"""
finnctl — finn.no client library and CLI tool.

Library usage::

    from finnctl import FinnClient, TorgetClient, MyItemsClient
    from finnctl import Session, load_session, save_session, clear_session, require_session

    # Search without authentication
    with FinnClient() as finn:
        results = TorgetClient(finn).search("sykkel", sort="newest")
        for ad in results.ads:
            print(ad.title, ad.price)

    # Access user's own ads (requires a saved session)
    from finnctl import require_session
    session = require_session()
    with FinnClient() as finn:
        ads = MyItemsClient(finn, session).fetch_all()
"""

from .auth import Session, load_session, save_session, clear_session, require_session
from .client import FinnClient, SearchAd, SearchResult, Coordinates
from .marketplaces.torget import TorgetClient
from .marketplaces.my_items import MyItemsClient
from .marketplaces.ad_cache import AdCache, CachedAd
from .marketplaces.ad_get import fetch_ad_payload, image_uris
from .marketplaces.ad_put import push_ad, pause_ad
from .marketplaces.my_items import fetch_ad_state

__all__ = [
    "FinnClient",
    "TorgetClient",
    "MyItemsClient",
    "AdCache",
    "CachedAd",
    "fetch_ad_payload",
    "image_uris",
    "push_ad",
    "pause_ad",
    "fetch_ad_state",
    "SearchAd",
    "SearchResult",
    "Coordinates",
    "Session",
    "load_session",
    "save_session",
    "clear_session",
    "require_session",
]
