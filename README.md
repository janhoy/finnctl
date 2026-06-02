# finnctl

A command-line tool for interacting with [finn.no](https://www.finn.no), Norway's largest classifieds marketplace.

Licensed under the [Apache License, Version 2.0](LICENSE.txt).

## Features

- **torget search** — Search the general Torget marketplace

More features are planned: managing your own active ads, viewing received messages, tracking saved searches, and support for additional marketplaces (bil, eiendom, etc.).

## Installation

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```sh
git clone <repo>
cd finn-tools
uv sync
```

Then run with:

```sh
uv run finnctl <command>
```

Or install globally:

```sh
uv tool install .
```

## Usage

### torget search

Search for items on Torget:

```sh
finnctl torget search skistaver
finnctl torget search "røde stoler" --limit 10
finnctl torget search sykkel --sort PRICE_ASC
finnctl torget search lego --page 2 --plain
```

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--limit` | `-n` | 20 | Number of results to show |
| `--page` | `-p` | 1 | Page number |
| `--sort` | `-s` | `PUBLISHED_DESC` | Sort order |
| `--plain` | | false | Plain text output (pipe-friendly) |

**Sort values:** `PUBLISHED_DESC`, `PUBLISHED_ASC`, `PRICE_ASC`, `PRICE_DESC`, `RELEVANCE`

The `--plain` flag outputs one result per line (`price  location  title`) suitable for piping to grep, awk, etc.
