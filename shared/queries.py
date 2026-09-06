"""Read-only queries for the Data Viewer and Data Analytics pages.

All functions accept a connection parameter and return plain dicts or
pandas DataFrames. No Streamlit or Plotly imports — this is pure business logic.
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import psycopg

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Ticker queries
# --------------------------------------------------------------------------- #

def get_all_tickers(conn: psycopg.Connection) -> list[dict]:
    """Return all tickers with metadata and sync status.

    JOINs tickers (constant metadata) with ticker_sync (mutable sync markers).

    Args:
        conn: Active database connection.

    Returns:
        List of dicts, one per ticker, with all metadata + sync fields.
    """
    rows = conn.execute("""
        SELECT
            t.ticker, t.name, t.sector, t.industry, t.currency,
            t.exchange, t.exchange_name, t.country, t.timezone,
            t.quote_type, t.is_active, t.created_at,
            s.last_synced_on, s.last_candle_date, s.updated_at
        FROM market.tickers t
        LEFT JOIN market.ticker_sync s ON t.ticker = s.ticker
        ORDER BY t.ticker
    """).fetchall()

    result: list[dict] = []
    for r in rows:
        result.append({
            "ticker": r[0],
            "name": r[1],
            "sector": r[2],
            "industry": r[3],
            "currency": r[4],
            "exchange": r[5],
            "exchange_name": r[6],
            "country": r[7],
            "timezone": r[8],
            "quote_type": r[9],
            "is_active": r[10],
            "created_at": r[11],
            "last_synced_on": r[12],
            "last_candle_date": r[13],
            "sync_updated_at": r[14],
        })
    logger.debug("Fetched %d tickers with metadata", len(result))
    return result


def get_ticker_detail(conn: psycopg.Connection, ticker: str) -> dict | None:
    """Return full metadata + sync status for a single ticker.

    Args:
        conn: Active database connection.
        ticker: Ticker symbol to look up.

    Returns:
        Dict with all metadata fields, or None if not found.
    """
    row = conn.execute("""
        SELECT
            t.ticker, t.name, t.sector, t.industry, t.currency,
            t.exchange, t.exchange_name, t.country, t.timezone,
            t.quote_type, t.is_active, t.created_at,
            s.last_synced_on, s.last_candle_date, s.updated_at
        FROM market.tickers t
        LEFT JOIN market.ticker_sync s ON t.ticker = s.ticker
        WHERE t.ticker = %s
    """, (ticker,)).fetchone()

    if row is None:
        return None

    return {
        "ticker": row[0],
        "name": row[1],
        "sector": row[2],
        "industry": row[3],
        "currency": row[4],
        "exchange": row[5],
        "exchange_name": row[6],
        "country": row[7],
        "timezone": row[8],
        "quote_type": row[9],
        "is_active": row[10],
        "created_at": row[11],
        "last_synced_on": row[12],
        "last_candle_date": row[13],
        "sync_updated_at": row[14],
    }


def get_tickers_with_stats(conn: psycopg.Connection) -> list[dict]:
    """Return each ticker with row counts for candles, dividends, splits.

    Args:
        conn: Active database connection.

    Returns:
        List of dicts with ticker metadata plus count fields.
    """
    rows = conn.execute("""
        SELECT
            t.ticker, t.name, t.sector, t.currency, t.exchange_name,
            s.last_synced_on, s.last_candle_date,
            COALESCE(c.candle_count, 0) AS candle_count,
            COALESCE(d.dividend_count, 0) AS dividend_count,
            COALESCE(sp.split_count, 0) AS split_count
        FROM market.tickers t
        LEFT JOIN market.ticker_sync s ON t.ticker = s.ticker
        LEFT JOIN (
            SELECT ticker, COUNT(*) AS candle_count
            FROM market.daily_candles GROUP BY ticker
        ) c ON t.ticker = c.ticker
        LEFT JOIN (
            SELECT ticker, COUNT(*) AS dividend_count
            FROM market.dividends GROUP BY ticker
        ) d ON t.ticker = d.ticker
        LEFT JOIN (
            SELECT ticker, COUNT(*) AS split_count
            FROM market.splits GROUP BY ticker
        ) sp ON t.ticker = sp.ticker
        ORDER BY t.ticker
    """).fetchall()

    result: list[dict] = []
    for r in rows:
        result.append({
            "ticker": r[0],
            "name": r[1],
            "sector": r[2],
            "currency": r[3],
            "exchange_name": r[4],
            "last_synced_on": r[5],
            "last_candle_date": r[6],
            "candle_count": r[7],
            "dividend_count": r[8],
            "split_count": r[9],
        })
    logger.debug("Fetched %d tickers with stats", len(result))
    return result


# --------------------------------------------------------------------------- #
# Candle queries
# --------------------------------------------------------------------------- #

def get_candles(
    conn: psycopg.Connection,
    ticker: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    """Return daily OHLCV for a ticker within an optional date range.

    Args:
        conn: Active database connection.
        ticker: Ticker symbol.
        start_date: Inclusive start date (None = no lower bound).
        end_date: Inclusive end date (None = no upper bound).

    Returns:
        List of candle dicts sorted by trade_date ascending.
    """
    conditions = ["ticker = %s"]
    params: list[object] = [ticker]

    if start_date is not None:
        conditions.append("trade_date >= %s")
        params.append(start_date)
    if end_date is not None:
        conditions.append("trade_date <= %s")
        params.append(end_date)

    where = " AND ".join(conditions)
    query = f"""
        SELECT trade_date, open, high, low, close, adj_close, volume
        FROM market.daily_candles
        WHERE {where}
        ORDER BY trade_date ASC
    """

    rows = conn.execute(query, params).fetchall()
    result: list[dict] = []
    for r in rows:
        result.append({
            "trade_date": r[0],
            "open": r[1],
            "high": r[2],
            "low": r[3],
            "close": r[4],
            "adj_close": r[5],
            "volume": r[6],
        })
    logger.debug("Fetched %d candles for %s (range: %s to %s)",
                 len(result), ticker, start_date, end_date)
    return result


def get_candles_df(
    conn: psycopg.Connection,
    ticker: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    """Return daily OHLCV as a pandas DataFrame.

    Same as get_candles but returns a DataFrame for analytics operations.

    Args:
        conn: Active database connection.
        ticker: Ticker symbol.
        start_date: Inclusive start date.
        end_date: Inclusive end date.

    Returns:
        DataFrame with columns: trade_date, open, high, low, close,
        adj_close, volume. Index is trade_date.
    """
    data = get_candles(conn, ticker, start_date, end_date)
    if not data:
        return pd.DataFrame(columns=["trade_date", "open", "high", "low",
                                     "close", "adj_close", "volume"])
    df = pd.DataFrame(data)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df.set_index("trade_date", inplace=True)
    return df


# --------------------------------------------------------------------------- #
# Dividend / Split queries
# --------------------------------------------------------------------------- #

def get_dividends(conn: psycopg.Connection, ticker: str) -> list[dict]:
    """Return dividend history for a ticker.

    Args:
        conn: Active database connection.
        ticker: Ticker symbol.

    Returns:
        List of dividend dicts sorted by pay_date ascending.
    """
    rows = conn.execute("""
        SELECT pay_date, amount
        FROM market.dividends
        WHERE ticker = %s
        ORDER BY pay_date ASC
    """, (ticker,)).fetchall()

    result: list[dict] = [{"pay_date": r[0], "amount": r[1]} for r in rows]
    logger.debug("Fetched %d dividends for %s", len(result), ticker)
    return result


def get_splits(conn: psycopg.Connection, ticker: str) -> list[dict]:
    """Return split history for a ticker.

    Args:
        conn: Active database connection.
        ticker: Ticker symbol.

    Returns:
        List of split dicts sorted by split_date ascending.
    """
    rows = conn.execute("""
        SELECT split_date, ratio
        FROM market.splits
        WHERE ticker = %s
        ORDER BY split_date ASC
    """, (ticker,)).fetchall()

    result: list[dict] = [{"split_date": r[0], "ratio": r[1]} for r in rows]
    logger.debug("Fetched %d splits for %s", len(result), ticker)
    return result


# --------------------------------------------------------------------------- #
# Aggregate / summary queries
# --------------------------------------------------------------------------- #

def get_sync_summary(conn: psycopg.Connection) -> dict:
    """Return aggregate stats: total tickers, data range, last sync time.

    Args:
        conn: Active database connection.

    Returns:
        Dict with keys: total_tickers, total_candles, total_dividends,
        total_splits, min_date, max_date, last_sync.
    """
    ticker_count = conn.execute(
        "SELECT COUNT(*) FROM market.tickers"
    ).fetchone()[0]

    candle_count = conn.execute(
        "SELECT COUNT(*) FROM market.daily_candles"
    ).fetchone()[0]

    dividend_count = conn.execute(
        "SELECT COUNT(*) FROM market.dividends"
    ).fetchone()[0]

    split_count = conn.execute(
        "SELECT COUNT(*) FROM market.splits"
    ).fetchone()[0]

    date_range = conn.execute("""
        SELECT MIN(trade_date), MAX(trade_date) FROM market.daily_candles
    """).fetchone()

    last_sync = conn.execute("""
        SELECT MAX(last_synced_on) FROM market.ticker_sync
    """).fetchone()[0]

    result = {
        "total_tickers": ticker_count,
        "total_candles": candle_count,
        "total_dividends": dividend_count,
        "total_splits": split_count,
        "min_date": date_range[0] if date_range else None,
        "max_date": date_range[1] if date_range else None,
        "last_sync": last_sync,
    }
    logger.debug("Sync summary: %s", result)
    return result


def get_multi_ticker_candles_df(
    conn: psycopg.Connection,
    tickers: list[str],
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    """Return close prices for multiple tickers as a single DataFrame.

    Useful for correlation analysis and multi-ticker comparison charts.

    Args:
        conn: Active database connection.
        tickers: List of ticker symbols.
        start_date: Inclusive start date.
        end_date: Inclusive end date.

    Returns:
        DataFrame with trade_date index and one column per ticker containing
        close prices.
    """
    if not tickers:
        return pd.DataFrame()

    placeholders = ", ".join(["%s"] * len(tickers))
    conditions = [f"ticker IN ({placeholders})"]
    params: list[object] = list(tickers)

    if start_date is not None:
        conditions.append("trade_date >= %s")
        params.append(start_date)
    if end_date is not None:
        conditions.append("trade_date <= %s")
        params.append(end_date)

    where = " AND ".join(conditions)
    query = f"""
        SELECT ticker, trade_date, close
        FROM market.daily_candles
        WHERE {where}
        ORDER BY trade_date ASC
    """

    rows = conn.execute(query, params).fetchall()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["ticker", "trade_date", "close"])
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    pivot = df.pivot(index="trade_date", columns="ticker", values="close")
    pivot.index.name = "trade_date"

    logger.debug("Fetched multi-ticker close prices: %d rows, %d tickers",
                 len(pivot), len(pivot.columns))
    return pivot
