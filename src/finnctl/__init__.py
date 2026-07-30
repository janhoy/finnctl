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

from .auth import Session, clear_session, load_session, require_session, save_session
from .client import Coordinates, FinnClient, SearchAd, SearchResult
from .marketplaces.ad_cache import AdCache, CachedAd
from .marketplaces.ad_get import fetch_ad_payload, image_uris
from .marketplaces.ad_put import pause_ad, push_ad
from .marketplaces.lettings import LettingsClient, RentalAd, RentalSearchResult
from .marketplaces.my_items import MyItemsClient, fetch_ad_state
from .marketplaces.realestate import HomeAd, HomeSearchResult, RealestateClient
from .marketplaces.torget import TorgetClient

__all__ = [
    "FinnClient",
    "TorgetClient",
    "RealestateClient",
    "HomeAd",
    "HomeSearchResult",
    "LettingsClient",
    "RentalAd",
    "RentalSearchResult",
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
