"""CLI commands for finn.no Torget (general marketplace)."""

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from rich import box
from rich.text import Text

from ..client import FinnClient
from ..marketplaces.torget import SORT_MAP, TorgetClient

app = typer.Typer(help="finn.no Torget — second-hand general marketplace.")
console = Console()
err = Console(stderr=True)

SORT_HELP = (
    "Sort order. Options: newest (default), oldest, relevance, "
    "price-asc, price-desc, distance. "
    "'distance' sorts by proximity to --location or your current IP location."
)


def _price_str(ad) -> str:
    if ad.price is None:
        return "–"
    if ad.price == 0:
        return "Gratis"
    return f"{ad.price:,} kr".replace(",", "\u202f")


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search terms")],
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of results to show")] = 20,
    page: Annotated[int, typer.Option("--page", "-p", help="Page number")] = 1,
    sort: Annotated[str, typer.Option("--sort", "-s", help=SORT_HELP)] = "newest",
    price_min: Annotated[int | None, typer.Option("--price-min", help="Minimum price (NOK)")] = None,
    price_max: Annotated[int | None, typer.Option("--price-max", help="Maximum price (NOK)")] = None,
    location: Annotated[
        str | None,
        typer.Option(
            "--location", "-l",
            help=(
                "Filter by location. Norwegian county/city names are recognised directly "
                "(e.g. Oslo, Akershus, Rogaland, Trondheim). "
                "Unknown names are geocoded via Nominatim and fall back to distance sort."
            ),
        ),
    ] = None,
    plain: Annotated[bool, typer.Option("--plain", help="Plain text output, one ad per line (pipe-friendly)")] = False,
) -> None:
    """Search for ads on Torget."""
    if sort not in SORT_MAP:
        err.print(
            f"[red]Unknown sort value:[/red] {sort!r}. "
            f"Valid options: {', '.join(SORT_MAP)}"
        )
        raise typer.Exit(1)

    coords = None
    if sort == "distance" and not location:
        # Auto-detect location from IP
        with FinnClient() as finn:
            coords = finn.get_ip_location()
        if coords:
            if not plain:
                console.print(
                    f"[dim]Detecting location via IP: {coords.city or f'{coords.lat:.2f},{coords.lon:.2f}'}[/dim]"
                )
        else:
            err.print("[yellow]Warning:[/yellow] Could not determine location via IP. Distance sort may be inaccurate.")

    with FinnClient() as finn:
        client = TorgetClient(finn)
        try:
            result = client.search(
                query,
                page=page,
                sort=sort,
                price_min=price_min,
                price_max=price_max,
                location=location,
                coords=coords,
            )
        except Exception as e:
            err.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    ads = result.ads[:limit]

    if not ads:
        console.print("No results found.")
        raise typer.Exit(0)

    if plain:
        for ad in ads:
            loc_str = ad.location or "–"
            print(f"{_price_str(ad):<14} {loc_str:<22} {ad.title}")
    else:
        # Build subtitle showing active filters
        filters: list[str] = []
        if location:
            filters.append(f"sted: {location}")
        if price_min is not None:
            filters.append(f"fra {price_min:,} kr".replace(",", "\u202f"))
        if price_max is not None:
            filters.append(f"til {price_max:,} kr".replace(",", "\u202f"))
        filter_str = f"  [{', '.join(filters)}]" if filters else ""

        total_str = f"{result.total:,}".replace(",", "\u202f") if result.total else "?"
        console.print(
            f"\n[bold]Torget:[/bold] [cyan]{query}[/cyan]{filter_str} — "
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
        table.add_column("Pris", justify="right", width=11, no_wrap=True)
        table.add_column("Sted", width=18, no_wrap=True, overflow="ellipsis")
        table.add_column("Tittel", overflow="ellipsis")

        for i, ad in enumerate(ads, start=1):
            title = Text(ad.title, no_wrap=True)
            title.stylize(f"link {ad.url}")
            table.add_row(str(i), _price_str(ad), ad.location or "–", title)

        console.print(table)
