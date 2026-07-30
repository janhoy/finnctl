"""Unit tests for the realestate (homes for sale) marketplace client.

These tests are fully offline: HTML parsing is exercised against inline
fixtures, and RealestateClient.search() is driven with a stub HTTP client so
no request ever hits finn.no.
"""

import pytest
from bs4 import BeautifulSoup

from finnctl.marketplaces.realestate import (
    HomeAd,
    RealestateClient,
    _extract_total,
    _parse_card,
    _to_int,
    resolve_ownership_type,
    resolve_property_type,
)

# nbsp — the digit-group separator finn.no uses in prices/areas.
NBSP = " "


# ── friendly-name resolvers ───────────────────────────────────────────────────

@pytest.mark.parametrize(
    "name,expected",
    [
        ("leilighet", 3),
        ("Leilighet", 3),   # case-insensitive
        ("enebolig", 1),
        ("hus", 1),         # alias for enebolig
        ("rekkehus", 4),
        ("7", 7),           # raw numeric code passes through
    ],
)
def test_resolve_property_type(name, expected):
    assert resolve_property_type(name) == expected


@pytest.mark.parametrize(
    "name,expected",
    [
        ("selveier", 3),
        ("eier", 3),
        ("borettslag", 4),
        ("andel", 4),
        ("aksje", 2),
    ],
)
def test_resolve_ownership_type(name, expected):
    assert resolve_ownership_type(name) == expected


def test_resolve_property_type_invalid():
    with pytest.raises(ValueError, match="Unknown property type"):
        resolve_property_type("villa")


def test_resolve_ownership_type_invalid():
    with pytest.raises(ValueError, match="Unknown ownership form"):
        resolve_ownership_type("leie")


# ── number extraction ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "text,expected",
    [
        (f"1{NBSP}700{NBSP}000 kr", 1_700_000),
        ("107 m²", 107),
        (f"Totalpris: 1{NBSP}743{NBSP}590 kr", 1_743_590),
        # Price range on new-development listings -> lower ("from") price.
        (f"5{NBSP}640{NBSP}000 - 6{NBSP}050{NBSP}000 kr", 5_640_000),
        ("", None),
        (None, None),
        ("ingen tall", None),
    ],
)
def test_to_int(text, expected):
    assert _to_int(text) == expected


# ── total-count extraction ────────────────────────────────────────────────────

def test_extract_total_treff():
    soup = BeautifulSoup("<div>Bolig til salgs <span>46 treff</span></div>", "html.parser")
    assert _extract_total(soup) == 46


def test_extract_total_boliger():
    soup = BeautifulSoup(f"<div>35{NBSP}448 boliger</div>", "html.parser")
    assert _extract_total(soup) == 35_448


def test_extract_total_missing():
    soup = BeautifulSoup("<div>ingenting her</div>", "html.parser")
    assert _extract_total(soup) == 0


# ── card parsing ──────────────────────────────────────────────────────────────

def _card(finnkode, *, link_id=True, title="Fin enebolig", area="107 m²",
          price="1 700 000 kr", total="Totalpris: 1 743 590 kr",
          meta="Selveier ∙ Enebolig ∙ 3 soverom", location="Snekkergata 2, Mjøndalen"):
    id_attr = f'id="{finnkode}"' if link_id else ""
    return f"""
    <article class="sf-search-ad card">
      <img src="https://images.finncdn.no/img/{finnkode}.jpg"/>
      <h2 class="sf-realestate-heading">
        <a class="sf-search-ad-link" href="/realestate/homes/ad.html?finnkode={finnkode}" {id_attr}>{title}</a>
      </h2>
      <div class="sf-realestate-location"><span>{location}</span></div>
      <span>{area}</span>
      <span>{price}</span>
      <span>{total}</span>
      <span>{meta}</span>
    </article>
    """


def test_parse_card_full():
    soup = BeautifulSoup(_card("470367807"), "html.parser")
    ad = _parse_card(soup.find("article"))
    assert isinstance(ad, HomeAd)
    assert ad.id == "470367807"
    assert ad.title == "Fin enebolig"
    assert ad.url == "https://www.finn.no/realestate/homes/ad.html?finnkode=470367807"
    assert ad.price == 1_700_000
    assert ad.total_price == 1_743_590
    assert ad.area_m2 == 107
    assert ad.bedrooms == 3
    assert ad.property_type == "Enebolig"
    assert ad.ownership == "Selveier"
    assert ad.location == "Snekkergata 2, Mjøndalen"
    assert ad.image_url.endswith("470367807.jpg")


def test_parse_card_project_price_range_and_no_bedrooms():
    """New-development cards show a price range and omit the bedroom count."""
    html = _card(
        "406537358",
        price="5 640 000 - 6 050 000 kr",
        total="Totalpris: 5 671 372 - 6 081 372 kr",
        meta="Selveier ∙ Enebolig",  # no "∙ N soverom"
    )
    ad = _parse_card(BeautifulSoup(html, "html.parser").find("article"))
    assert ad.price == 5_640_000          # lower bound of the range
    assert ad.total_price == 5_671_372
    assert ad.bedrooms is None
    assert ad.ownership == "Selveier"
    assert ad.property_type == "Enebolig"


def test_parse_card_without_link_returns_none():
    soup = BeautifulSoup('<article class="sf-search-ad"><span>no link</span></article>', "html.parser")
    assert _parse_card(soup.find("article")) is None


# ── search() param building & dedup (stubbed HTTP) ────────────────────────────

class _StubFinn:
    """Stands in for FinnClient; records the params and returns a fixed soup."""

    def __init__(self, html: str):
        self._soup = BeautifulSoup(html, "html.parser")
        self.last_params: dict | None = None

    def get_page(self, path, params=None):
        self.last_params = params
        return self._soup


def test_search_builds_params_and_maps_codes():
    stub = _StubFinn("<div>0 treff</div>")
    RealestateClient(stub).search(
        "enebolig",
        sort="price-asc",
        price_min=2_000_000,
        price_max=8_000_000,
        property_types=["hus", "leilighet"],
        ownership_types=["borettslag"],
        bedrooms_min=8,       # above the facet max -> must clamp
        area_min=60,
        location="Oslo",
    )
    p = stub.last_params
    assert p["q"] == "enebolig"
    assert p["sort"] == "PRICE_ASC"
    assert p["price_from"] == 2_000_000
    assert p["price_to"] == 8_000_000
    assert p["property_type"] == [1, 3]     # hus->1, leilighet->3
    assert p["ownership_type"] == [4]       # borettslag->4
    assert p["min_bedrooms"] == 5           # clamped from 8 to the "5+" max
    assert p["area_from"] == 60
    assert p["location"] == "0.20061"       # Oslo county code


def test_search_deduplicates_featured_card():
    """The featured top card duplicates a real listing (same finnkode)."""
    # First card has no id (featured), second is the real one — same finnkode.
    html = "<div>2 treff</div>" + _card("111", link_id=False) + _card("111") + _card("222")
    result = RealestateClient(_StubFinn(html)).search()
    ids = [a.id for a in result.ads]
    assert ids == ["111", "222"]            # 111 collapsed to a single entry


def test_search_location_raw_code_passthrough():
    stub = _StubFinn("<div>0 treff</div>")
    RealestateClient(stub).search(location="2.20007.20110.23007")
    assert stub.last_params["location"] == "2.20007.20110.23007"
