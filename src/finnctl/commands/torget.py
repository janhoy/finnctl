"""CLI commands for finn.no Torget (general marketplace)."""

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from rich import box
from rich.text import Text

from ..client import FinnClient
from ..marketplaces.torget import TorgetClient

app = typer.Typer(help="finn.no Torget — second-hand general marketplace.")
console = Console()


def _price_str(ad) -> str:
    if ad.price is None:
        return "–"
    if ad.price == 0:
        return "Gratis"
    return f"{ad.price:,} kr".replace(",", "\u202f")


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search terms")],
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of results")] = 20,
    page: Annotated[int, typer.Option("--page", "-p", help="Page number")] = 1,
    sort: Annotated[
        str,
        typer.Option(
            "--sort",
            "-s",
            help="Sort order: PUBLISHED_DESC, PUBLISHED_ASC, PRICE_ASC, PRICE_DESC, RELEVANCE",
        ),
    ] = "PUBLISHED_DESC",
    plain: Annotated[bool, typer.Option("--plain", help="Plain text output, one ad per line")] = False,
) -> None:
    """Search for ads on Torget."""
    with FinnClient() as finn:
        client = TorgetClient(finn)
        try:
            result = client.search(query, page=page, sort=sort)
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}", err=True)
            raise typer.Exit(1)

    ads = result.ads[:limit]

    if not ads:
        console.print("No results found.")
        raise typer.Exit(0)

    if plain:
        for ad in ads:
            location_str = ad.location or "–"
            print(f"{_price_str(ad):<14} {location_str:<22} {ad.title}")
    else:
        total_str = f"{result.total:,}".replace(",", "\u202f") if result.total else "?"
        console.print(
            f"\n[bold]Torget:[/bold] [cyan]{query}[/cyan] — "
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
            table.add_row(
                str(i),
                _price_str(ad),
                ad.location or "–",
                title,
            )

        console.print(table)
