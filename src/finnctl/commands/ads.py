"""CLI commands for managing finn.no ads."""

from typing import Annotated

import typer
from rich.console import Console

from ..auth import require_session
from ..client import FinnClient
from ..marketplaces.ad_cache import AdCache
from ..marketplaces.ad_get import fetch_ad_payload, image_uris, marketplace_from_payload
from ..marketplaces.ad_put import pause_ad, push_ad
from ..marketplaces.my_items import MyItemsClient, STATE_MAP, fetch_ad_state

app = typer.Typer(help="Manage your finn.no ads.")
console = Console()
err = Console(stderr=True)

# ── cache sub-group ───────────────────────────────────────────────────────────

_cache_app = typer.Typer(help="Manage locally cached ads (~/.finnctl/cache/).")
app.add_typer(_cache_app, name="cache")


@_cache_app.command("list")
def cache_list() -> None:
    """List all locally cached ads."""
    ads = AdCache.list()
    if not ads:
        console.print("No cached ads. Run [bold]finnctl ads get <id>[/bold] to cache one.")
        return
    console.print(f"Cached ads ({len(ads)}):\n")
    for ad in ads:
        date = ad.cached_at[:10] if ad.cached_at else "–"
        images = len(list((ad.folder / "images").glob("*"))) if (ad.folder / "images").exists() else 0
        print(f"{ad.name:<20} {ad.finn_id:<12} {date}  {images}img  {ad.title[:50]}")


@_cache_app.command("delete")
def cache_delete(
    id_or_name: Annotated[str, typer.Argument(help="Finn ID or cache name to delete")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Delete a locally cached ad."""
    try:
        folder = AdCache.find(id_or_name)
    except FileNotFoundError:
        err.print(f"[red]Not found:[/red] no cached ad for {id_or_name!r}")
        raise typer.Exit(1)

    if not yes:
        typer.confirm(f"Delete cache at {folder}?", abort=True)

    deleted = AdCache.delete(id_or_name)
    console.print(f"Deleted {deleted}")


# ── ads list ──────────────────────────────────────────────────────────────────

_VALID_STATES = list(STATE_MAP.keys())


@app.command("list")
def ads_list(
    marketplace: Annotated[
        str | None,
        typer.Option("--marketplace", "-m", help="Filter by marketplace (torget, bil, eiendom …)"),
    ] = None,
    state: Annotated[
        str,
        typer.Option("--state", "-s", help=f"Filter by ad state: {', '.join(_VALID_STATES)}"),
    ] = "active",
) -> None:
    """List your ads."""
    if state not in STATE_MAP:
        err.print(f"[red]Invalid state:[/red] {state!r}. Valid: {', '.join(_VALID_STATES)}")
        raise typer.Exit(1)

    try:
        session = require_session()
    except RuntimeError as e:
        err.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    with FinnClient() as finn:
        client = MyItemsClient(finn, session)
        try:
            result = client.fetch_all(marketplace=marketplace, state=state)
        except Exception as e:
            err.print(f"[red]Error fetching ads:[/red] {e}")
            raise typer.Exit(1)

    ads = result.ads
    if not ads:
        console.print(f"No ads found{' for ' + marketplace if marketplace else ''}.")
        raise typer.Exit(0)

    mp_str = f" [{marketplace}]" if marketplace else ""
    state_str = f" ({state})" if state != "active" else ""
    console.print(f"My ads{mp_str}{state_str} — {len(ads)} found")

    for ad in ads:
        print(f"{ad.finn_id:<12} {ad.marketplace:<12} {(ad.status or '–'):<10} {_fmt_date(ad.updated):<11} {ad.title}")


def _fmt_date(iso: str | None) -> str:
    return iso[:10] if iso else "–"


# ── ads get ───────────────────────────────────────────────────────────────────

@app.command("get")
def ads_get(
    finn_id: Annotated[str, typer.Argument(help="Finn ad ID to download")],
    name: Annotated[
        str | None,
        typer.Option("--name", "-n", help="Folder name to use instead of the finn ID"),
    ] = None,
) -> None:
    """Download a full ad and its images to ~/.finnctl/cache/."""
    try:
        session = require_session()
    except RuntimeError as e:
        err.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    console.print(f"Fetching ad {finn_id}…")
    with FinnClient() as finn:
        try:
            payload = fetch_ad_payload(finn, session, finn_id)
        except Exception as e:
            err.print(f"[red]Could not fetch ad {finn_id}:[/red] {e}")
            raise typer.Exit(1)

    uris = image_uris(payload)
    mp = marketplace_from_payload(payload)
    title = payload.get("data", {}).get("title", "")

    console.print(f"  {title}")
    console.print(f"  {len(uris)} image(s) — downloading…")

    folder = AdCache.save(finn_id, payload, uris, name=name, marketplace=mp)
    console.print(f"[green]Saved[/green] → {folder}")


# ── ads pause ─────────────────────────────────────────────────────────────────

@app.command("pause")
def ads_pause(
    id_or_name: Annotated[str, typer.Argument(help="Finn ID or cache name to pause")],
) -> None:
    """Pause (delist) an active ad without deleting it."""
    try:
        session = require_session()
    except RuntimeError as e:
        err.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    with FinnClient() as finn:
        finn_id = id_or_name
        try:
            import json as _json
            folder = AdCache.find(id_or_name)
            meta = _json.loads((folder / "meta.json").read_text())
            finn_id = str(meta["finn_id"])
        except Exception:
            pass

        try:
            pause_ad(finn, session, finn_id)
        except Exception as e:
            err.print(f"[red]Failed to pause ad {finn_id}:[/red] {e}")
            raise typer.Exit(1)

    console.print(f"[green]Ad {finn_id} paused.[/green]")


# ── ads put ───────────────────────────────────────────────────────────────────

@app.command("put")
def ads_put(
    id_or_name: Annotated[str, typer.Argument(help="Finn ID or cache name to upload")],
    price: Annotated[
        int | None,
        typer.Option("--price", "-p", help="Override price (NOK)"),
    ] = None,
) -> None:
    """
    Push a cached ad back to finn.no via the edit API.

    Updates the ad's content (title, description, images, price) and leaves it
    inactive — visit the returned URL in your browser to publish.
    """
    try:
        payload = AdCache.load_ad(id_or_name)
    except FileNotFoundError:
        err.print(f"[red]Not cached:[/red] run 'finnctl ads get {id_or_name}' first")
        raise typer.Exit(1)

    # Resolve finn_id from meta
    try:
        folder = AdCache.find(id_or_name)
        import json
        meta = json.loads((folder / "meta.json").read_text())
        finn_id = str(meta["finn_id"])
    except Exception as e:
        err.print(f"[red]Could not read cache metadata:[/red] {e}")
        raise typer.Exit(1)

    try:
        session = require_session()
    except RuntimeError as e:
        err.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    if price is not None:
        console.print(f"Updating price to {price:,} kr…".replace(",", "\u202f"))

    console.print(f"Pushing ad {finn_id} to finn.no…")
    with FinnClient() as finn:
        try:
            edit_url = push_ad(finn, session, finn_id, payload, price=price)
        except Exception as e:
            err.print(f"[red]Failed to push ad:[/red] {e}")
            raise typer.Exit(1)

    console.print(f"[green]Done.[/green] Open to review and publish:")
    console.print(f"  {edit_url}")


# ── ads republish ─────────────────────────────────────────────────────────────

EDIT_URL_BASE = "https://www.finn.no/recommerce/create"


@app.command("republish")
def ads_republish(
    id_or_name: Annotated[str, typer.Argument(help="Finn ID or cache name to republish")],
    name: Annotated[
        str | None,
        typer.Option("--name", "-n", help="Cache folder name (defaults to finn ID)"),
    ] = None,
    price: Annotated[
        int | None,
        typer.Option("--price", "-p", help="Override price (NOK)"),
    ] = None,
) -> None:
    """
    Re-list an ad on finn.no.

    For expired ads: just opens the finn.no edit page (no re-upload needed).
    For active ads: pauses the existing ad, then re-uploads it as a new listing.
    Use --price to change the price at the same time.
    """
    try:
        session = require_session()
    except RuntimeError as e:
        err.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    with FinnClient() as finn:
        # Resolve finn_id if a cache name was given
        finn_id = id_or_name
        try:
            import json as _json
            folder = AdCache.find(id_or_name)
            meta = _json.loads((folder / "meta.json").read_text())
            finn_id = str(meta["finn_id"])
        except Exception:
            pass  # id_or_name is already a finn_id

        # Check current state
        try:
            state = fetch_ad_state(finn, session, finn_id)
        except Exception as e:
            err.print(f"[red]Could not check ad state:[/red] {e}")
            raise typer.Exit(1)

        edit_url = f"{EDIT_URL_BASE}/{finn_id}"

        if state == "EXPIRED":
            # Expired ads: finn still has all the data — just open the edit page.
            # Only need to re-upload if the user wants to change the price.
            if price is not None:
                _republish_via_upload(finn, session, finn_id, id_or_name, name, price)
            else:
                console.print(f"Ad {finn_id} is expired — no re-upload needed.")
                console.print(f"[green]Open to review and publish:[/green]")
                console.print(f"  {edit_url}")

        elif state == "ACTIVE":
            # Active ads: pause first, then re-upload with a fresh listing.
            console.print(f"Pausing active ad {finn_id}…")
            try:
                pause_ad(finn, session, finn_id)
            except Exception as e:
                err.print(f"[red]Failed to pause ad:[/red] {e}")
                raise typer.Exit(1)
            console.print("[green]Ad paused.[/green]")

            _republish_via_upload(finn, session, finn_id, id_or_name, name, price)

        else:
            err.print(f"[red]Cannot republish ad in state {state!r}.[/red]")
            raise typer.Exit(1)


def _republish_via_upload(
    finn: FinnClient,
    session,
    finn_id: str,
    id_or_name: str,
    name: str | None,
    price: int | None,
) -> None:
    """Fetch the ad, cache it, optionally tweak the text, and push it back."""
    console.print(f"Fetching ad {finn_id}…")
    try:
        payload = fetch_ad_payload(finn, session, finn_id)
    except Exception as e:
        err.print(f"[red]Could not fetch ad {finn_id}:[/red] {e}")
        raise typer.Exit(1)

    # Slightly modify description to avoid finn's duplicate-ad detection
    data = payload.setdefault("data", {})
    desc = data.get("description", "")
    if desc and not desc.endswith("."):
        data["description"] = desc + "."

    uris = image_uris(payload)
    mp = marketplace_from_payload(payload)
    title = data.get("title", "")

    console.print(f"  {title}")
    console.print(f"  {len(uris)} image(s) — downloading…")

    folder = AdCache.save(finn_id, payload, uris, name=name, marketplace=mp)
    console.print(f"[green]Cached[/green] → {folder}")

    if price is not None:
        console.print(f"Updating price to {price:,} kr…".replace(",", "\u202f"))

    console.print(f"Pushing ad {finn_id} to finn.no…")
    try:
        edit_url = push_ad(finn, session, finn_id, payload, price=price)
    except Exception as e:
        err.print(f"[red]Failed to push ad:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"[green]Done.[/green] Open to review and publish:")
    console.print(f"  {edit_url}")
