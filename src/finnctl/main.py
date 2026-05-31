"""finnctl — CLI tool for finn.no classifieds."""

import typer

from .commands import torget as torget_cmd

app = typer.Typer(
    name="finnctl",
    help="CLI tool for finn.no classifieds.",
    no_args_is_help=True,
)

app.add_typer(torget_cmd.app, name="torget")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
