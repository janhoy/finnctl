"""CLI commands for finn.no lettings (bolig til leie / homes for rent)."""

import json as jsonlib
from typing import Annotated

import typer
from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from ..client import FinnClient
from ..marketplaces.lettings import (
    PROPERTY_TYPES,
    SORT_MAP,
    LettingsClient,
    resolve_property_type,
)

app = typer.Typer(help="finn.no Eiendom — bolig til leie (homes for rent).")
console = Console()
err = Console(stderr=True)

SORT_HELP = (
    "Sort order. Options: newest (default), price-asc, price-desc, "
    "area-asc, area-desc, relevance. (price = monthly rent)"
)
TYPE_HELP = (
    "Property type (repeatable). Options: "
    + ", ".join(sorted(set(PROPERTY_TYPES)))
    + "."
)


def _rent_str(value: int | None) -> str:
    if value is None:
        return "–"
    return f"{value:,} kr".replace(",", " ")


@app.command()
def search(
    query: Annotated[str | None, typer.Argument(help="Keywords (optional)")] = None,
    price_min: Annotated[int | None, typer.Option("--price-min", help="Minimum monthly rent (NOK)")] = None,
    price_max: Annotated[int | None, typer.Option("--price-max", help="Maximum monthly rent (NOK)")] = None,
    property_type: Annotated[
        list[str] | None,
        typer.Option("--type", "-t", help=TYPE_HELP),
    ] = None,
    bedrooms_min: Annotated[int | None, typer.Option("--bedrooms-min", "-b", help="Minimum number of bedrooms")] = None,
    area_min: Annotated[int | None, typer.Option("--area-min", help="Minimum living area (m²)")] = None,
    location: Annotated[
        str | None,
        typer.Option(
            "--location", "-l",
            help=(
                "Location filter. Accepts a finn.no location code "
                "(e.g. 2.20007.20110.23007) or a county name (e.g. Oslo, Buskerud)."
            ),
        ),
    ] = None,
    sort: Annotated[str, typer.Option("--sort", "-s", help=SORT_HELP)] = "newest",
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of results to show")] = 20,
    page: Annotated[int, typer.Option("--page", "-p", help="Page number")] = 1,
    json_out: Annotated[bool, typer.Option("--json", help="Output results as JSON")] = False,
    plain: Annotated[bool, typer.Option("--plain", help="Plain text output, one ad per line")] = False,
) -> None:
    """Search homes for rent on finn.no."""
    if sort not in SORT_MAP:
        err.print(f"[red]Unknown sort value:[/red] {sort!r}. Valid: {', '.join(SORT_MAP)}")
        raise typer.Exit(1)

    # Validate friendly names early so the user gets a clear error.
    try:
        if property_type:
            for t in property_type:
                resolve_property_type(t)
    except ValueError as e:
        err.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    with FinnClient() as finn:
        client = LettingsClient(finn)
        try:
            result = client.search(
                query,
                page=page,
                sort=sort,
                price_min=price_min,
                price_max=price_max,
                property_types=property_type,
                bedrooms_min=bedrooms_min,
                area_min=area_min,
                location=location,
            )
        except Exception as e:
            err.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    ads = result.ads[:limit]

    if json_out:
        payload = {"total": result.total, "page": result.page, "ads": [a.to_dict() for a in ads]}
        print(jsonlib.dumps(payload, ensure_ascii=False, indent=2))
        raise typer.Exit(0)

    if not ads:
        console.print("No results found.")
        raise typer.Exit(0)

    if plain:
        for ad in ads:
            print(
                f"{_rent_str(ad.rent):<13} "
                f"{(ad.property_type or '–'):<20} "
                f"{(str(ad.bedrooms) + ' sov' if ad.bedrooms is not None else '–'):<7} "
                f"{(ad.location or '–'):<28} {ad.title}"
            )
        raise typer.Exit(0)

    # Filter summary line
    filters: list[str] = []
    if query:
        filters.append(f"«{query}»")
    if property_type:
        filters.append("/".join(property_type))
    if bedrooms_min is not None:
        filters.append(f"≥{bedrooms_min} sov")
    if price_min is not None:
        filters.append(f"fra {_rent_str(price_min)}")
    if price_max is not None:
        filters.append(f"til {_rent_str(price_max)}")
    if location:
        filters.append(f"sted: {location}")
    filter_str = f"  [{', '.join(filters)}]" if filters else ""

    total_str = f"{result.total:,}".replace(",", " ") if result.total else "?"
    console.print(
        f"\n[bold]Bolig til leie[/bold]{filter_str} — "
        f"viser {len(ads)} av {total_str} treff (side {page})\n"
    )

    table = Table(
        box=box.SIMPLE,
        show_header=True,
        header_style="bold cyan",
        show_edge=False,
        padding=(0, 1),
    )
    table.add_column("#", style="dim", width=3, justify="right", no_wrap=True)
    table.add_column("Leie/mnd", justify="right", width=11, no_wrap=True)
    table.add_column("Type", width=18, no_wrap=True, overflow="ellipsis")
    table.add_column("Sov", justify="right", width=3, no_wrap=True)
    table.add_column("Areal", justify="right", width=7, no_wrap=True)
    table.add_column("Sted", width=22, no_wrap=True, overflow="ellipsis")
    table.add_column("Tittel", overflow="ellipsis")

    for i, ad in enumerate(ads, start=1):
        title = Text(ad.title, no_wrap=True)
        title.stylize(f"link {ad.url}")
        table.add_row(
            str(i),
            _rent_str(ad.rent),
            ad.property_type or "–",
            str(ad.bedrooms) if ad.bedrooms is not None else "–",
            f"{ad.area_m2} m²" if ad.area_m2 is not None else "–",
            ad.location or "–",
            title,
        )

    console.print(table)
