"""finnctl — CLI tool for finn.no classifieds."""

import typer

from .commands import ads as ads_cmd
from .commands import auth as auth_cmd
from .commands import torget as torget_cmd

app = typer.Typer(
    name="finnctl",
    help="CLI tool for finn.no classifieds. Library: `from finnctl import FinnClient`.",
    no_args_is_help=True,
)

app.add_typer(torget_cmd.app, name="torget")
app.add_typer(ads_cmd.app, name="ads")
app.add_typer(auth_cmd.app, name="auth")

# Top-level shortcuts: `finnctl login` / `finnctl logout` / `finnctl whoami`
app.command("login")(auth_cmd.login)
app.command("logout")(auth_cmd.logout)
app.command("whoami")(auth_cmd.whoami)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
