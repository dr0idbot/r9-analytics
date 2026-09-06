"""Database layer for r9_analytics market ingestion.

- Provides a psycopg (v3) connection helper
- All SQL is defined ONCE as module-level parameterised constants so
  ingestion and query code never rebuilds query strings at runtime.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

import psycopg

from shared.config import load_db_config

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Connection management
# --------------------------------------------------------------------------- #
@contextmanager
def get_connection(config: dict | None = None) -> Iterator[psycopg.Connection]:
    """Yield a psycopg connection (autocommit off; caller commits).

    Args:
        config: DB config dict. If None, loads from dbconf.yaml.

    Yields:
        An open psycopg Connection.
    """
    cfg = config or load_db_config()
    logger.debug("Connecting to %s@%s:%s/%s", cfg["user"], cfg["host"], cfg["port"], cfg["dbname"])
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

# --- portfolios ------------------------------------------------------------- #
Q_CREATE_PORTFOLIOS = """
CREATE TABLE IF NOT EXISTS market.portfolios (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    currency    TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW()
)
"""

Q_CREATE_PORTFOLIO_SECURITIES = """
CREATE TABLE IF NOT EXISTS market.portfolio_securities (
    portfolio_id  INT NOT NULL REFERENCES market.portfolios(id) ON DELETE CASCADE,
    ticker        TEXT NOT NULL REFERENCES market.tickers(ticker),
    buy_price     NUMERIC(12,4) NOT NULL,
    buy_date      DATE NOT NULL,
    units         INT NOT NULL,
    PRIMARY KEY (portfolio_id, ticker)
)
"""

Q_INSERT_PORTFOLIO = """
INSERT INTO market.portfolios (name, currency)
VALUES (%(name)s, %(currency)s)
RETURNING id
"""

Q_SELECT_PORTFOLIO = """
SELECT id, name, currency, created_at FROM market.portfolios WHERE id = %s
"""

Q_SELECT_PORTFOLIO_BY_NAME = """
SELECT id, name, currency, created_at FROM market.portfolios WHERE name = %s
"""

Q_LIST_PORTFOLIOS = """
SELECT p.id, p.name, p.currency, p.created_at,
       COUNT(ps.ticker) AS security_count
FROM market.portfolios p
LEFT JOIN market.portfolio_securities ps ON ps.portfolio_id = p.id
GROUP BY p.id
ORDER BY p.name
"""

Q_DELETE_PORTFOLIO = """
DELETE FROM market.portfolios WHERE id = %s
"""

Q_UPSERT_PORTFOLIO_SECURITY = """
INSERT INTO market.portfolio_securities (portfolio_id, ticker, buy_price, buy_date, units)
VALUES (%(portfolio_id)s, %(ticker)s, %(buy_price)s, %(buy_date)s, %(units)s)
ON CONFLICT (portfolio_id, ticker) DO UPDATE SET
    buy_price = EXCLUDED.buy_price,
    buy_date = EXCLUDED.buy_date,
    units = EXCLUDED.units
"""

Q_DELETE_PORTFOLIO_SECURITY = """
DELETE FROM market.portfolio_securities
WHERE portfolio_id = %s AND ticker = %s
"""

Q_GET_PORTFOLIO_SECURITIES = """
SELECT ps.ticker, ps.buy_price, ps.buy_date, ps.units,
       t.name, t.sector, t.industry, t.currency
FROM market.portfolio_securities ps
JOIN market.tickers t ON t.ticker = ps.ticker
WHERE ps.portfolio_id = %s
ORDER BY (ps.units * ps.buy_price) DESC
"""

Q_GET_TICKER_CURRENCY = """
SELECT currency FROM market.tickers WHERE ticker = %s
"""

Q_LIST_CURRENCIES = """
SELECT DISTINCT currency FROM market.tickers WHERE currency IS NOT NULL ORDER BY currency
"""

# --- calc schema (persisted calculation results) ---------------------------- #
Q_CREATE_CALC_SCHEMA = "CREATE SCHEMA IF NOT EXISTS calc"

Q_CREATE_RISK_METRICS = """
CREATE TABLE IF NOT EXISTS calc.risk_metrics (
    id              SERIAL PRIMARY KEY,
    ticker          TEXT NOT NULL,
    calc_time       TIMESTAMP NOT NULL DEFAULT NOW(),
    -- Phase 1: Risk
    realized_volatility     DOUBLE PRECISION,
    parkinson_volatility    DOUBLE PRECISION,
    garman_klass_volatility DOUBLE PRECISION,
    semi_deviation          DOUBLE PRECISION,
    downside_ratio          DOUBLE PRECISION,
    max_drawdown            DOUBLE PRECISION,
    historical_var_95       DOUBLE PRECISION,
    parametric_var_95       DOUBLE PRECISION,
    cvar_95                 DOUBLE PRECISION,
    -- Phase 2: Risk-Adjusted Return
    sharpe_ratio            DOUBLE PRECISION,
    sortino_ratio           DOUBLE PRECISION,
    calmar_ratio            DOUBLE PRECISION,
    treynor_ratio           DOUBLE PRECISION,
    information_ratio       DOUBLE PRECISION,
    omega_ratio             DOUBLE PRECISION,
    beta                    DOUBLE PRECISION,
    UNIQUE (ticker, calc_time)
)
"""

Q_INSERT_RISK_METRICS = """
INSERT INTO calc.risk_metrics
    (ticker, calc_time,
     realized_volatility, parkinson_volatility, garman_klass_volatility,
     semi_deviation, downside_ratio, max_drawdown,
     historical_var_95, parametric_var_95, cvar_95,
     sharpe_ratio, sortino_ratio, calmar_ratio,
     treynor_ratio, information_ratio, omega_ratio, beta)
VALUES
    (%(ticker)s, %(calc_time)s,
     %(realized_volatility)s, %(parkinson_volatility)s, %(garman_klass_volatility)s,
     %(semi_deviation)s, %(downside_ratio)s, %(max_drawdown)s,
     %(historical_var_95)s, %(parametric_var_95)s, %(cvar_95)s,
     %(sharpe_ratio)s, %(sortino_ratio)s, %(calmar_ratio)s,
     %(treynor_ratio)s, %(information_ratio)s, %(omega_ratio)s, %(beta)s)
"""

Q_GET_LATEST_RISK_METRICS = """
SELECT ticker, calc_time,
       realized_volatility, parkinson_volatility, garman_klass_volatility,
       semi_deviation, downside_ratio, max_drawdown,
       historical_var_95, parametric_var_95, cvar_95,
       sharpe_ratio, sortino_ratio, calmar_ratio,
       treynor_ratio, information_ratio, omega_ratio, beta
FROM calc.risk_metrics
WHERE ticker = %s
ORDER BY calc_time DESC
LIMIT 1
"""

Q_GET_RISK_METRICS_HISTORY = """
SELECT ticker, calc_time,
       realized_volatility, parkinson_volatility, garman_klass_volatility,
       semi_deviation, downside_ratio, max_drawdown,
       historical_var_95, parametric_var_95, cvar_95,
       sharpe_ratio, sortino_ratio, calmar_ratio,
       treynor_ratio, information_ratio, omega_ratio, beta
FROM calc.risk_metrics
WHERE ticker = %s
ORDER BY calc_time DESC
"""


# --------------------------------------------------------------------------- #
# Thin helpers (use the constants above; keep call sites tidy)
# --------------------------------------------------------------------------- #
def upsert_ticker(conn: psycopg.Connection, meta: dict) -> None:
    """Upsert constant metadata for a ticker."""
    conn.execute(Q_UPSERT_TICKER, meta)


def upsert_sync(
    conn: psycopg.Connection,
    ticker: str,
    last_synced_on: object,
    last_candle_date: object,
) -> None:
    """Update sync markers for a ticker."""
    conn.execute(
        Q_UPSERT_SYNC,
        {
            "ticker": ticker,
            "last_synced_on": last_synced_on,
            "last_candle_date": last_candle_date,
        },
    )


def upsert_candle(conn: psycopg.Connection, row: dict) -> None:
    """Upsert a single daily candle row."""
    conn.execute(Q_INSERT_CANDLE, row)


def upsert_dividend(conn: psycopg.Connection, row: dict) -> None:
    """Upsert a single dividend event."""
    conn.execute(Q_INSERT_DIVIDEND, row)


def upsert_split(conn: psycopg.Connection, row: dict) -> None:
    """Upsert a single split event."""
    conn.execute(Q_INSERT_SPLIT, row)


def all_tickers(conn: psycopg.Connection) -> list[str]:
    """Return sorted list of all ticker symbols in the database."""
    return [r[0] for r in conn.execute(Q_ALL_TICKERS).fetchall()]


def max_candle_date(conn: psycopg.Connection, ticker: str) -> object:
    """Return the most recent trade_date for a ticker, or None."""
    return conn.execute(Q_MAX_CANDLE_DATE, (ticker,)).fetchone()[0]


# --- portfolio helpers ------------------------------------------------------ #
def ensure_portfolio_tables(conn: psycopg.Connection) -> None:
    """Create portfolio tables if they do not exist."""
    conn.execute(Q_CREATE_PORTFOLIOS)
    conn.execute(Q_CREATE_PORTFOLIO_SECURITIES)


def insert_portfolio(conn: psycopg.Connection, name: str, currency: str) -> int:
    """Create a portfolio and return its id."""
    row = conn.execute(Q_INSERT_PORTFOLIO, {"name": name, "currency": currency}).fetchone()
    return row[0]


def get_portfolio(conn: psycopg.Connection, portfolio_id: int) -> dict | None:
    """Return portfolio metadata or None."""
    row = conn.execute(Q_SELECT_PORTFOLIO, (portfolio_id,)).fetchone()
    if row is None:
        return None
    return {"id": row[0], "name": row[1], "currency": row[2], "created_at": row[3]}


def get_portfolio_by_name(conn: psycopg.Connection, name: str) -> dict | None:
    """Return portfolio metadata by name or None."""
    row = conn.execute(Q_SELECT_PORTFOLIO_BY_NAME, (name,)).fetchone()
    if row is None:
        return None
    return {"id": row[0], "name": row[1], "currency": row[2], "created_at": row[3]}


def list_portfolios(conn: psycopg.Connection) -> list[dict]:
    """Return all portfolios with security count."""
    return [
        {"id": r[0], "name": r[1], "currency": r[2], "created_at": r[3], "security_count": r[4]}
        for r in conn.execute(Q_LIST_PORTFOLIOS).fetchall()
    ]


def delete_portfolio(conn: psycopg.Connection, portfolio_id: int) -> None:
    """Delete a portfolio and its securities (cascade)."""
    conn.execute(Q_DELETE_PORTFOLIO, (portfolio_id,))


def upsert_portfolio_security(
    conn: psycopg.Connection, portfolio_id: int, ticker: str,
    buy_price: float, buy_date: object, units: int
) -> None:
    """Add or update a security in a portfolio."""
    conn.execute(
        Q_UPSERT_PORTFOLIO_SECURITY,
        {"portfolio_id": portfolio_id, "ticker": ticker,
         "buy_price": buy_price, "buy_date": buy_date, "units": units},
    )


def delete_portfolio_security(conn: psycopg.Connection, portfolio_id: int, ticker: str) -> None:
    """Remove a security from a portfolio."""
    conn.execute(Q_DELETE_PORTFOLIO_SECURITY, (portfolio_id, ticker))


def get_portfolio_securities(conn: psycopg.Connection, portfolio_id: int) -> list[dict]:
    """Return securities in a portfolio with ticker metadata."""
    return [
        {
            "ticker": r[0], "buy_price": float(r[1]), "buy_date": r[2],
            "units": int(r[3]), "name": r[4], "sector": r[5],
            "industry": r[6], "currency": r[7],
        }
        for r in conn.execute(Q_GET_PORTFOLIO_SECURITIES, (portfolio_id,)).fetchall()
    ]


def get_ticker_currency(conn: psycopg.Connection, ticker: str) -> str | None:
    """Return the currency of a ticker, or None if not found."""
    row = conn.execute(Q_GET_TICKER_CURRENCY, (ticker,)).fetchone()
    return row[0] if row else None


def list_currencies(conn: psycopg.Connection) -> list[str]:
    """Return distinct currencies from the tickers table."""
    return [r[0] for r in conn.execute(Q_LIST_CURRENCIES).fetchall()]


# --- calc helpers ----------------------------------------------------------- #
def ensure_calc_schema(conn: psycopg.Connection) -> None:
    """Create calc schema and tables if they do not exist."""
    conn.execute(Q_CREATE_CALC_SCHEMA)
    conn.execute(Q_CREATE_RISK_METRICS)


def insert_risk_metrics(conn: psycopg.Connection, data: dict) -> None:
    """Insert a risk metrics record."""
    conn.execute(Q_INSERT_RISK_METRICS, data)


def get_latest_risk_metrics(conn: psycopg.Connection, ticker: str) -> dict | None:
    """Return the most recent risk metrics for a ticker, or None."""
    row = conn.execute(Q_GET_LATEST_RISK_METRICS, (ticker,)).fetchone()
    if row is None:
        return None
    return {
        "ticker": row[0], "calc_time": row[1],
        "realized_volatility": row[2], "parkinson_volatility": row[3],
        "garman_klass_volatility": row[4], "semi_deviation": row[5],
        "downside_ratio": row[6], "max_drawdown": row[7],
        "historical_var_95": row[8], "parametric_var_95": row[9],
        "cvar_95": row[10],
        "sharpe_ratio": row[11], "sortino_ratio": row[12],
        "calmar_ratio": row[13], "treynor_ratio": row[14],
        "information_ratio": row[15], "omega_ratio": row[16],
        "beta": row[17],
    }


def get_risk_metrics_history(conn: psycopg.Connection, ticker: str) -> list[dict]:
    """Return all risk metrics records for a ticker, newest first."""
    rows = conn.execute(Q_GET_RISK_METRICS_HISTORY, (ticker,)).fetchall()
    return [
        {
            "ticker": r[0], "calc_time": r[1],
            "realized_volatility": r[2], "parkinson_volatility": r[3],
            "garman_klass_volatility": r[4], "semi_deviation": r[5],
            "downside_ratio": r[6], "max_drawdown": r[7],
            "historical_var_95": r[8], "parametric_var_95": r[9],
            "cvar_95": r[10],
            "sharpe_ratio": r[11], "sortino_ratio": r[12],
            "calmar_ratio": r[13], "treynor_ratio": r[14],
            "information_ratio": r[15], "omega_ratio": r[16],
            "beta": r[17],
        }
        for r in rows
    ]
