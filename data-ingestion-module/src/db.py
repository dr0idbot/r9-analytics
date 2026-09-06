"""Database layer for r9_analytics market ingestion.

- Loads config/dbconf.yaml
- Provides a psycopg (v3) connection helper
- All SQL is defined ONCE as module-level parameterised constants so the
  ingestion script never rebuilds query strings at runtime.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "dbconf.yaml"


# --------------------------------------------------------------------------- #
# Config loading
# --------------------------------------------------------------------------- #
def load_db_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, "r") as fh:
        return yaml.safe_load(fh)


# --------------------------------------------------------------------------- #
# Connection management
# --------------------------------------------------------------------------- #
@contextmanager
def get_connection(config: dict | None = None) -> Iterator[psycopg.Connection]:
    """Yield a psycopg connection (autocommit off; caller commits)."""
    cfg = config or load_db_config()
    conn = psycopg.connect(
        host=cfg["host"],
        port=cfg["port"],
        dbname=cfg["dbname"],
        user=cfg["user"],
        password=cfg["password"],
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Parameterised query constants (defined once, reused everywhere)
# --------------------------------------------------------------------------- #

# --- tickers (constant metadata) ------------------------------------------- #
Q_UPSERT_TICKER = """
INSERT INTO market.tickers
    (ticker, name, sector, industry, currency, exchange,
     exchange_name, country, timezone, quote_type, is_active)
VALUES
    (%(ticker)s, %(name)s, %(sector)s, %(industry)s, %(currency)s,
     %(exchange)s, %(exchange_name)s, %(country)s, %(timezone)s,
     %(quote_type)s, %(is_active)s)
ON CONFLICT (ticker) DO UPDATE SET
    name = EXCLUDED.name,
    sector = EXCLUDED.sector,
    industry = EXCLUDED.industry,
    currency = EXCLUDED.currency,
    exchange = EXCLUDED.exchange,
    exchange_name = EXCLUDED.exchange_name,
    country = EXCLUDED.country,
    timezone = EXCLUDED.timezone,
    quote_type = EXCLUDED.quote_type
"""

Q_TICKER_EXISTS = """
SELECT 1 FROM market.tickers WHERE ticker = %s
"""

Q_ALL_TICKERS = """
SELECT ticker FROM market.tickers ORDER BY ticker
"""

# --- ticker_sync (mutable sync markers) ------------------------------------ #
Q_UPSERT_SYNC = """
INSERT INTO market.ticker_sync (ticker, last_synced_on, last_candle_date, updated_at)
VALUES (%(ticker)s, %(last_synced_on)s, %(last_candle_date)s, NOW())
ON CONFLICT (ticker) DO UPDATE SET
    last_synced_on = EXCLUDED.last_synced_on,
    last_candle_date = EXCLUDED.last_candle_date,
    updated_at = NOW()
"""

Q_GET_SYNC = """
SELECT last_synced_on, last_candle_date
FROM market.ticker_sync WHERE ticker = %s
"""

# --- daily_candles (OHLCV) ------------------------------------------------- #
Q_INSERT_CANDLE = """
INSERT INTO market.daily_candles
    (ticker, trade_date, open, high, low, close, adj_close, volume)
VALUES
    (%(ticker)s, %(trade_date)s, %(open)s, %(high)s, %(low)s,
     %(close)s, %(adj_close)s, %(volume)s)
ON CONFLICT (ticker, trade_date) DO UPDATE SET
    open = EXCLUDED.open,
    high = EXCLUDED.high,
    low = EXCLUDED.low,
    close = EXCLUDED.close,
    adj_close = EXCLUDED.adj_close,
    volume = EXCLUDED.volume
"""

Q_MAX_CANDLE_DATE = """
SELECT MAX(trade_date) FROM market.daily_candles WHERE ticker = %s
"""

# --- dividends / splits ---------------------------------------------------- #
Q_INSERT_DIVIDEND = """
INSERT INTO market.dividends (ticker, pay_date, amount)
VALUES (%(ticker)s, %(pay_date)s, %(amount)s)
ON CONFLICT (ticker, pay_date) DO UPDATE SET amount = EXCLUDED.amount
"""

Q_INSERT_SPLIT = """
INSERT INTO market.splits (ticker, split_date, ratio)
VALUES (%(ticker)s, %(split_date)s, %(ratio)s)
ON CONFLICT (ticker, split_date) DO UPDATE SET ratio = EXCLUDED.ratio
"""


# --------------------------------------------------------------------------- #
# Thin helpers (use the constants above; keep call sites tidy)
# --------------------------------------------------------------------------- #
def upsert_ticker(conn: psycopg.Connection, meta: dict) -> None:
    conn.execute(Q_UPSERT_TICKER, meta)


def upsert_sync(
    conn: psycopg.Connection,
    ticker: str,
    last_synced_on,
    last_candle_date,
) -> None:
    conn.execute(
        Q_UPSERT_SYNC,
        {
            "ticker": ticker,
            "last_synced_on": last_synced_on,
            "last_candle_date": last_candle_date,
        },
    )


def upsert_candle(conn: psycopg.Connection, row: dict) -> None:
    conn.execute(Q_INSERT_CANDLE, row)


def upsert_dividend(conn: psycopg.Connection, row: dict) -> None:
    conn.execute(Q_INSERT_DIVIDEND, row)


def upsert_split(conn: psycopg.Connection, row: dict) -> None:
    conn.execute(Q_INSERT_SPLIT, row)


def all_tickers(conn: psycopg.Connection) -> list[str]:
    return [r[0] for r in conn.execute(Q_ALL_TICKERS).fetchall()]


def max_candle_date(conn: psycopg.Connection, ticker: str):
    return conn.execute(Q_MAX_CANDLE_DATE, (ticker,)).fetchone()[0]


if __name__ == "__main__":
    # Smoke test: confirm we can connect and read the schema.
    with get_connection() as conn:
        n = conn.execute("SELECT COUNT(*) FROM market.tickers").fetchone()[0]
        print(f"Connected. tickers rows = {n}")
