# finnctl

A command-line tool for interacting with [finn.no](https://www.finn.no), Norway's largest classifieds marketplace.

Licensed under the [Apache License, Version 2.0](LICENSE.txt).

## Features

- **torget search** — Search the general Torget marketplace
- **realestate search** — Search *Bolig til salgs* (homes for sale) with filters

More features are planned: managing your own active ads, viewing received messages, tracking saved searches, and support for additional marketplaces (bil, etc.).

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

### realestate search

Search *Bolig til salgs* (homes for sale). Filter by keywords, price, property
type, number of bedrooms, ownership form, living area, and location. The
command is also available under its Norwegian alias `eiendom`.

```sh
finnctl realestate search --type leilighet --ownership selveier --bedrooms-min 2 --location Oslo --price-max 6000000
finnctl realestate search enebolig --bedrooms-min 3 --location 2.20007.20110.23007
finnctl realestate search --type leilighet --type rekkehus --location Oslo --json
finnctl eiendom search hytte --price-min 2000000 --plain
```

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--price-min` | | | Minimum asking price (NOK) |
| `--price-max` | | | Maximum asking price (NOK) |
| `--type` | `-t` | | Property type (repeatable) |
| `--bedrooms-min` | `-b` | | Minimum number of bedrooms |
| `--ownership` | `-o` | | Ownership form (repeatable) |
| `--area-min` | | | Minimum living area (m²) |
| `--location` | `-l` | | Location code or county name |
| `--sort` | `-s` | `newest` | Sort order |
| `--limit` | `-n` | 20 | Number of results to show |
| `--page` | `-p` | 1 | Page number |
| `--json` | | false | Output structured JSON |
| `--plain` | | false | Plain text output (pipe-friendly) |

**Property types:** `leilighet`, `enebolig` (alias `hus`), `tomannsbolig`, `rekkehus`, `garasje`

**Ownership forms:** `selveier` (alias `eier`), `borettslag` (alias `andel`), `aksje`, `obligasjon`

**Sort values:** `newest`, `oldest`, `price-asc`, `price-desc`, `area-asc`, `area-desc`

**Location:** pass a finn.no location code — the leading digit is the depth,
so `0.` = county, `1.` = municipality, `2.` = district (e.g.
`2.20007.20110.23007` = Buskerud › Drammen › Nedre Eiker). County names such as
`Oslo` or `Buskerud` are also recognised directly.

**Structured output:** `--json` emits `{ "total", "page", "ads": [...] }` where
each ad includes `id`, `title`, `url`, `price`, `total_price`, `location`,
`area_m2`, `bedrooms`, `property_type`, and `ownership` — suitable for scripting
or piping to `jq`. The library API returns the same data as dataclasses:

```python
from finnctl import FinnClient
from finnctl.marketplaces.realestate import RealestateClient

with FinnClient() as finn:
    result = RealestateClient(finn).search(
        "enebolig", property_types=["hus"], bedrooms_min=3, price_max=5_000_000
    )
    for ad in result.ads:
        print(ad.price, ad.location, ad.title)
```
