# INFO.md — Market Data Ingestion Module

> Handover document for a new agent session. Read this first to understand
> what exists, how it is structured, and how to extend it.

## What this module does

Ingests daily market data from **yfinance** into a **PostgreSQL** database.
It is an interactive CLI that runs indefinitely, letting an operator
`update` all tracked tickers or `add` new ones. All data writes use
parameterised upserts so re-runs are idempotent (safe to run repeatedly).

## Directory layout

```
data-ingestion-module/
├── INFO.md                 # this file
├── requirements.txt        # psycopg>=3.1, pyyaml>=6.0, yfinance>=1.5
├── sql/
│   └── create_tables.sql   # schema: market.tickers, ticker_sync,
│                           #         daily_candles, dividends, splits
├── config/
│   ├── dbconf.yaml         # DB connection (host/port/db/user/pass/schema)
│   └── tickers.csv         # ROSTER: ticker,last_synced_on,last_candle_date
└── src/
    ├── main.py             # interactive CLI entry point
    ├── db.py               # psycopg connection + ALL SQL as constants
    ├── ingest.py           # yfinance fetch + smart-sync write logic
    ├── roster.py           # read/write config/tickers.csv
    └── logging_setup.py    # colored logging, level via --LOG
```

## Schema (Postgres, schema `market`)

- **`tickers`** — CONSTANT metadata only (name, sector, industry, currency,
  exchange, country, timezone, quote_type). PK `ticker`. Never changes after
  insert (so it stays a stable reference).
- **`ticker_sync`** — mutable per-ticker sync markers
  (`last_synced_on`, `last_candle_date`). Kept separate from `tickers`
  on purpose to preserve the "constant metadata" rule.
- **`daily_candles`** — OHLCV, PK `(ticker, trade_date)`, index on `trade_date`.
- **`dividends`** — PK `(ticker, pay_date)`.
- **`splits`** — PK `(ticker, split_date)`.
- All fact tables FK → `tickers` with `ON DELETE CASCADE`.

> **DB privileges note:** the `market` schema is owned by `postgres`. If you
> ever rebuild from scratch as a non-superuser, the app user `r9analyticsadmin`
> needs `GRANT CREATE, USAGE ON SCHEMA market` **and** ownership of the tables
> (otherwise index creation / writes fail). See `sql/create_tables.sql`.

## How smart sync works

1. `tickers.csv` is the **authoritative roster** of what to track.
2. On `add SYMBOL`, the symbol is checked for tradability on yfinance; if
   available it is appended to the CSV (empty sync dates) and an initial
   **full** sync (`period=max`) is run immediately.
3. On `update`, for each roster row we call `sync_ticker(..., resume_from=last_candle_date)`
   so only data **after** the last stored candle date is fetched. The CSV
   `last_candle_date` / `last_synced_on` are rewritten after each run.
4. All writes use `ON CONFLICT ... DO UPDATE`, so overlapping/duplicate rows
   are harmless.

## How to run

```bash
cd data-ingestion-module
pip install -r requirements.txt
PYTHONPATH=data-ingestion-module/src python3 data-ingestion-module/src/main.py --LOG DEBUG
```

Menu commands:
- `update` — sync every ticker in `tickers.csv` with latest data
- `add SYMBOL` — add a new ticker to the roster (if tradable)
- `list` — show roster + sync state
- `exit` — quit (also Ctrl-C / EOF is handled gracefully)

Log level is set with `--LOG DEBUG|INFO|WARNING|ERROR` (default `DEBUG`).
Every task logs `==> START`, per-ticker progress, and `<== FINISH` with
elapsed time and row counts.

## Connection / config

`config/dbconf.yaml` currently points at the local DB:
`r9analyticsadmin @ r9_analytics` (schema `market`). The password is stored
in plaintext in that file — for production, prefer env-var injection.

## Module responsibilities (where to change things)

- **`db.py`** — add any new SQL query as a module-level constant here; never
  build queries at runtime. `get_connection()` is a context manager that
  commits on success, rolls back on error.
- **`ingest.py`** — pure fetch/write logic. Add new data types (e.g.
  `financials`, `options`) here as new `fetch_*` + upsert functions, reusing
  the constants in `db.py`.
- **`roster.py`** — CSV roster IO. Change column handling here if the roster
  format evolves.
- **`main.py`** — CLI loop, menu parsing, logging orchestration, timing.
  Add new menu commands here; wrap them in `timed_task()`.

## Current state (as of handover)

- `tickers.csv` contains: `MSFT` (synced through 2026-08-21).
- `AAPL` exists in the DB from earlier testing but is **not** in the CSV
  roster, so `update` will not touch it until `add AAPL` is run.
- Verified: `add` (full sync), `update` (smart incremental sync), and CSV
  persistence all work against live yfinance.

## Known limitations / possible next steps

- No `remove` command (to drop a ticker from the roster + optionally the DB).
- No rate-limit / retry handling for yfinance (large rosters may get throttled).
- `tickers.csv` is the single source of truth; there is no command to seed it
  from the existing `tickers` table.
- DB password is in plaintext config (see above).
- No automated/scheduled run (cron or scheduler) — it is strictly interactive.
