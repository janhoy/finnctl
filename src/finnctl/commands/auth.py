"""CLI commands: login, logout, whoami."""

import plistlib
import subprocess
import sys
import webbrowser
from pathlib import Path

import httpx
import typer
from rich.console import Console

from ..auth import (
    FINN_LOGIN_URL,
    Session,
    clear_session,
    load_session,
    save_session,
)

app = typer.Typer(help="Log in/out of finn.no.")
console = Console()
err = Console(stderr=True)

_MANUAL_INSTRUCTIONS = """\
[bold]Could not read cookies from your browser automatically.[/bold]

To log in manually:

  1. Log in to finn.no in the browser that opens now.

  2. Open [bold]DevTools[/bold] (F12 or Cmd+Option+I) → [bold]Network[/bold] tab.

  3. Reload any finn.no page (e.g. finn.no/min-finn).

  4. Click any request → [bold]Request Headers[/bold] → find [bold]cookie[/bold].

  5. Right-click → [bold]Copy value[/bold], then paste below.
"""

# Maps bundle-id/desktop-file fragments → browser-cookie3 function names
_BUNDLE_MAP = {
    "vivaldi":  "vivaldi",
    "firefox":  "firefox",
    "chrome":   "chrome",
    "chromium": "chromium",
    "brave":    "brave",
    "edge":     "edge",
    "safari":   "safari",
    "opera":    "opera",
    "arc":      "arc",
}


# ── Default browser detection ─────────────────────────────────────────────────

def _detect_default_browser() -> str | None:
    """
    Return a browser-cookie3 function name for the system default browser,
    or None if it cannot be determined.
    """
    if sys.platform == "darwin":
        try:
            plist_path = (
                Path.home()
                / "Library/Preferences/com.apple.LaunchServices"
                / "com.apple.launchservices.secure.plist"
            )
            with open(plist_path, "rb") as f:
                data = plistlib.load(f)
            for handler in data.get("LSHandlers", []):
                if handler.get("LSHandlerURLScheme") == "https":
                    bundle = handler.get("LSHandlerRoleAll", "").lower()
                    for fragment, name in _BUNDLE_MAP.items():
                        if fragment in bundle:
                            return name
        except Exception:
            pass

    elif sys.platform.startswith("linux"):
        try:
            desktop = subprocess.check_output(
                ["xdg-settings", "get", "default-web-browser"],
                text=True, stderr=subprocess.DEVNULL,
            ).strip().lower()
            for fragment, name in _BUNDLE_MAP.items():
                if fragment in desktop:
                    return name
        except Exception:
            pass

    elif sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice",
            )
            prog_id = winreg.QueryValueEx(key, "ProgId")[0].lower()
            for fragment, name in _BUNDLE_MAP.items():
                if fragment in prog_id:
                    return name
        except Exception:
            pass

    return None


# ── Browser cookie extraction ─────────────────────────────────────────────────

def _extract_browser_cookies() -> str | None:
    """
    Read finn.no session cookies from the system default browser only.
    Falls back to Firefox if the default cannot be determined (Firefox
    does not require a keychain prompt on macOS).
    Returns a Cookie header string, or None.
    """
    try:
        import browser_cookie3
    except ImportError:
        return None

    browser_name = _detect_default_browser()
    candidates = [browser_name] if browser_name else []

    # Firefox is keychain-free — safe to try as a fallback without prompting
    if "firefox" not in candidates:
        candidates.append("firefox")

    for name in candidates:
        loader = getattr(browser_cookie3, name, None)
        if loader is None:
            continue
        try:
            jar = loader(domain_name=".finn.no")
            cookies = {c.name: c.value for c in jar if c.value}
            if cookies:
                label = name.capitalize()
                console.print(f"[dim]Found finn.no cookies in {label}.[/dim]")
                return "; ".join(f"{k}={v}" for k, v in cookies.items())
        except Exception:
            continue

    return None


def _validate_cookie(cookie: str) -> bool:
    """Return True if the cookie gives an authenticated response from finn.no."""
    try:
        r = httpx.get(
            "https://www.finn.no/frontpage-layout-v2/podium-resource/header/api",
            headers={"Cookie": cookie, "User-Agent": "finnctl/0.1"},
            timeout=httpx.Timeout(8.0),
            follow_redirects=False,
        )
        return r.status_code == 200 and bool(r.json().get("loginId"))
    except Exception:
        return False


def _identity_from_cookie(cookie: str) -> dict:
    """Fetch loginId / spidId / email from finn.no's header API."""
    try:
        r = httpx.get(
            "https://www.finn.no/frontpage-layout-v2/podium-resource/header/api",
            headers={"Cookie": cookie, "User-Agent": "finnctl/0.1"},
            timeout=httpx.Timeout(8.0),
            follow_redirects=False,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}


# ── Interactive fallback ──────────────────────────────────────────────────────

def _prompt_cookie() -> str:
    """Prompt the user to paste their finn.no cookie string; retry if blank."""
    while True:
        console.print("[bold cyan]Paste cookie value here:[/bold cyan] ", end="")
        value = sys.stdin.readline().strip()
        if value:
            return value
        console.print("[red]No value entered. Please try again.[/red]")


# ── typer commands ────────────────────────────────────────────────────────────

@app.callback(invoke_without_command=True)
def _root(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        ctx.invoke(login)


@app.command()
def login(
    force: bool = typer.Option(False, "--force", "-f", help="Re-authenticate even if a session already exists."),
) -> None:
    """Log in to finn.no — reads session from your default browser, or falls back to cookie paste."""
    existing = load_session()
    if existing and not force:
        who = existing.email or (f"loginId {existing.login_id}" if existing.login_id else "unknown")
        console.print(f"[green]Already logged in[/green] as {who}.")
        console.print("Run [bold]finnctl logout[/bold] to log out, or [bold]finnctl login --force[/bold] to re-authenticate.")
        raise typer.Exit(0)

    # 1. Try reading cookies from the system default browser
    browser_name = _detect_default_browser()
    console.print(
        f"Looking for existing finn.no session in "
        f"{browser_name.capitalize() if browser_name else 'your browser'}…"
    )
    cookie = _extract_browser_cookies()

    if cookie and _validate_cookie(cookie):
        identity = _identity_from_cookie(cookie)
        session = Session(
            cookie=cookie,
            login_id=identity.get("loginId"),
            spid_id=identity.get("spidId"),
            email=identity.get("email") or identity.get("displayName"),
        )
        save_session(session)
        who = session.email or (f"loginId {session.login_id}" if session.login_id else "unknown")
        console.print(f"[green]Logged in[/green] as {who} (from browser session).")
        return

    if cookie:
        console.print("[yellow]Found browser cookies but they appear to be logged out.[/yellow]")

    # 2. Fall back to manual browser open + cookie paste
    console.print(_MANUAL_INSTRUCTIONS)
    webbrowser.open(FINN_LOGIN_URL)

    try:
        cookie = _prompt_cookie()
    except (KeyboardInterrupt, EOFError):
        err.print("\n[yellow]Login cancelled.[/yellow]")
        raise typer.Exit(1)

    session = Session(cookie=cookie)
    save_session(session)
    console.print("[green]Session saved.[/green] Run [bold]finnctl whoami[/bold] to verify.")


@app.command()
def logout() -> None:
    """Log out and delete the saved session."""
    session = load_session()
    if session is None:
        console.print("Not logged in.")
        raise typer.Exit(0)
    clear_session()
    who = session.email or (f"loginId {session.login_id}" if session.login_id else "unknown")
    console.print(f"Logged out ({who}).")


@app.command()
def whoami() -> None:
    """Show the currently logged-in user."""
    session = load_session()
    if session is None:
        console.print("[yellow]Not logged in.[/yellow] Run [bold]finnctl login[/bold].")
        raise typer.Exit(1)

    if not session.login_id:
        identity = _identity_from_cookie(session.cookie)
        if identity.get("loginId"):
            session.login_id = identity.get("loginId")
            session.spid_id = identity.get("spidId")
            session.email = identity.get("email") or identity.get("displayName")
            save_session(session)

    console.print(f"Email:   {session.email or '–'}")
    console.print(f"LoginId: {session.login_id or '–'}")
    console.print(f"SpidId:  {session.spid_id or '–'}")
    console.print(f"Session: [green]active[/green] (cookie-based)")
