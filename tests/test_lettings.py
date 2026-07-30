"""Unit tests for the lettings (homes for rent) marketplace client.

Fully offline: HTML parsing runs against inline fixtures and search() is driven
with a stub HTTP client, so no request ever reaches finn.no.
"""

import pytest
from bs4 import BeautifulSoup

from finnctl.marketplaces.lettings import (
    SORT_MAP,
    LettingsClient,
    RentalAd,
    _parse_card,
    resolve_property_type,
)

# ── friendly-name resolver ────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "name,expected",
    [
        ("leilighet", 3),
        ("hus", 1),          # alias for enebolig
        ("hybel", 16),       # lettings-specific
        ("bofellesskap", 17),
        ("hytte", 12),
        ("18", 18),          # raw numeric passes through
    ],
)
def test_resolve_property_type(name, expected):
    assert resolve_property_type(name) == expected


def test_resolve_property_type_invalid():
    with pytest.raises(ValueError, match="Unknown property type"):
        resolve_property_type("sommerhus")


def test_sort_map_uses_rent_keys():
    # Rentals sort on RENT_*, not PRICE_*.
    assert SORT_MAP["price-asc"] == "RENT_ASC"
    assert SORT_MAP["price-desc"] == "RENT_DESC"
    assert SORT_MAP["newest"] == "PUBLISHED_DESC"


# ── card parsing ──────────────────────────────────────────────────────────────

def _card(finnkode, *, link_id=True, title="Fin leilighet",
          area="55 m²", rent="13 000 kr", meta="Leilighet ∙ 1 soverom",
          location="Tyrilia 5, Gamle Fredrikstad", agent="Privat"):
    id_attr = f'id="{finnkode}"' if link_id else ""
    return f"""
    <article class="sf-search-ad card">
      <img src="https://images.finncdn.no/dynamic/480w/item/{finnkode}/abc"/>
      <div class="p-16">
        <span>{agent}</span>
        <h2 class="sf-realestate-heading">
          <a class="sf-search-ad-link" href="/realestate/lettings/ad.html?finnkode={finnkode}" {id_attr}>{title}</a>
        </h2>
        <div class="sf-realestate-location"><span>{location}</span></div>
        <span>{area}</span>
        <span>{rent}</span>
        <span>{meta}</span>
      </div>
    </article>
    """


def test_parse_card_full():
    ad = _parse_card(BeautifulSoup(_card("471439862"), "html.parser").find("article"))
    assert isinstance(ad, RentalAd)
    assert ad.id == "471439862"
    assert ad.title == "Fin leilighet"
    assert ad.url == "https://www.finn.no/realestate/lettings/ad.html?finnkode=471439862"
    assert ad.rent == 13_000
    assert ad.area_m2 == 55
    assert ad.bedrooms == 1
    assert ad.property_type == "Leilighet"
    assert ad.location == "Tyrilia 5, Gamle Fredrikstad"
    assert ad.image_url.endswith("/abc")
    # Rentals have no ownership / total price.
    assert not hasattr(ad, "ownership")
    assert not hasattr(ad, "total_price")


def test_parse_card_type_only_no_bedrooms():
    """A card whose meta line is just the type (no '∙ N soverom')."""
    ad = _parse_card(BeautifulSoup(_card("111", meta="Leilighet"), "html.parser").find("article"))
    assert ad.property_type == "Leilighet"
    assert ad.bedrooms is None


def test_parse_card_multiword_type():
    ad = _parse_card(
        BeautifulSoup(_card("222", meta="Rom i bofellesskap ∙ 1 soverom"), "html.parser").find("article")
    )
    assert ad.property_type == "Rom i bofellesskap"
    assert ad.bedrooms == 1


def test_parse_card_agent_name_not_mistaken_for_type():
    """A landlord span like 'Hybel.no' must not be read as the property type."""
    ad = _parse_card(
        BeautifulSoup(_card("333", agent="Hybel.no", meta="Leilighet"), "html.parser").find("article")
    )
    assert ad.property_type == "Leilighet"


# ── search() param building & dedup (stubbed HTTP) ────────────────────────────

class _StubFinn:
    def __init__(self, html: str):
        self._soup = BeautifulSoup(html, "html.parser")
        self.last_params: dict | None = None

    def get_page(self, path, params=None):
        self.last_params = params
        return self._soup


def test_search_builds_params_and_maps_codes():
    stub = _StubFinn("<div>0 treff</div>")
    LettingsClient(stub).search(
        "sentralt",
        sort="price-asc",
        price_min=8_000,
        price_max=20_000,
        property_types=["hybel", "leilighet"],
        bedrooms_min=7,       # above the facet max -> must clamp to 5
        area_min=30,
        location="Oslo",
    )
    p = stub.last_params
    assert p["q"] == "sentralt"
    assert p["sort"] == "RENT_ASC"            # rent, not price
    assert p["price_from"] == 8_000
    assert p["price_to"] == 20_000
    assert p["property_type"] == [16, 3]      # hybel->16, leilighet->3
    assert p["min_bedrooms"] == 5             # clamped from 7
    assert p["area_from"] == 30
    assert p["location"] == "0.20061"         # Oslo county code
    assert "ownership_type" not in p          # rentals have no ownership form


def test_search_deduplicates_featured_card():
    html = "<div>2 treff</div>" + _card("111", link_id=False) + _card("111") + _card("222")
    result = LettingsClient(_StubFinn(html)).search()
    assert [a.id for a in result.ads] == ["111", "222"]
