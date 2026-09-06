# Market Data Ingestion Module

Interactive CLI that ingests daily market data from **yfinance** into
**PostgreSQL**. Re-runs are idempotent (upserts), so it is safe to run
repeatedly. See `INFO.md` for architecture and handover details.

## Requirements

```bash
pip install -r requirements.txt
# psycopg>=3.1, pyyaml>=6.0, yfinance>=1.5
```

You also need a reachable PostgreSQL database. Connection is configured in
`config/dbconf.yaml` (default points at the local `r9_analytics` DB,
schema `market`).

## Run

```bash
cd data-ingestion-module
PYTHONPATH=data-ingestion-module/src python3 data-ingestion-module/src/main.py [--LOG LEVEL]
```

## Parameters

| Parameter | Required | Default   | Choices                         | Description                                            |
|-----------|----------|-----------|---------------------------------|--------------------------------------------------------|
| `--LOG`   | No       | `DEBUG`   | `DEBUG`, `INFO`, `WARNING`, `ERROR` | Logging verbosity. Output is colored; every task logs start, progress, and finish with elapsed time + row counts. |

No other command-line arguments exist. Everything else is driven by the
interactive menu.

## Interactive menu

Once running, the script loops until you `exit`:

| Command       | Description                                                                 |
|---------------|-----------------------------------------------------------------------------|
| `update`      | Sync every ticker in `config/tickers.csv` with the latest data (smart/incremental). |
| `add SYMBOL`  | Add `SYMBOL` to the roster only if it is tradable on yfinance, then do a full initial sync. |
| `list`        | Show the roster with `last_synced_on` / `last_candle_date` for each ticker. |
| `exit`        | Quit (Ctrl-C / EOF also handled gracefully).                                |

Example session:
```
r9> list
r9> add NVDA
r9> update
r9> exit
```

## Configuration files

- **`config/dbconf.yaml`** — `host`, `port`, `dbname`, `user`, `password`, `schema`.
  Edit to point at your database.
- **`config/tickers.csv`** — the authoritative roster. Columns:
  `ticker,last_synced_on,last_candle_date`. `last_candle_date` is used as the
  resume point for smart sync on subsequent `update` runs. You normally do not
  edit this by hand; `add` / `update` maintain it automatically.

## Smart sync (what happens on `update`)

For each roster ticker, only data **after** its stored `last_candle_date` is
fetched, then the CSV and DB sync markers are updated. The first sync for a
newly added ticker is a full history pull (`period=max`).

## Notes

- Default log level is `DEBUG`; use `--LOG INFO` (or `WARNING`) for less noise.
- The DB password is stored in plaintext in `config/dbconf.yaml`; for
  production prefer environment-variable injection.
