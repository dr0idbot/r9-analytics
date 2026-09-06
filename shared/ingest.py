"""yfinance ingestion logic.

Pure data-fetching + DB-writing. No CLI, no logging side effects beyond
returning stats dicts so the caller can report timing/counts.
Reuses the parameterised query constants from db.py — no query is rebuilt here.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import yfinance as yf

from shared.db import (
    max_candle_date,
    upsert_candle,
    upsert_dividend,
    upsert_split,
    upsert_sync,
    upsert_ticker,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Metadata
# --------------------------------------------------------------------------- #
def fetch_ticker_meta(symbol: str) -> dict | None:
    """Pull CONSTANT metadata from yfinance .info and shape it for tickers.

    Returns None when the symbol cannot be resolved (delisted / 404 / no data)
    so the caller can skip it instead of crashing.

    Args:
        symbol: Yahoo Finance ticker symbol (e.g. "MSFT", "TCS.NS").

    Returns:
        Dict with ticker metadata keys, or None if unavailable.
    """
    try:
        info = yf.Ticker(symbol).info
    except Exception:
        return None
    if not info:
        return None
    if not (
        info.get("shortName")
        or info.get("longName")
        or info.get("currency")
        or info.get("timeZoneFullName")
        or info.get("exchangeTimezoneName")
        or info.get("exchange")
    ):
        return None
    return {
        "ticker": symbol.upper(),
        "name": info.get("shortName") or info.get("longName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "currency": info.get("currency"),
        "exchange": info.get("exchange"),
        "exchange_name": info.get("fullExchangeName"),
        "country": info.get("country"),
        "timezone": info.get("timeZoneFullName") or info.get("exchangeTimezoneName"),
        "quote_type": info.get("quoteType"),
        "is_active": True,
    }


# --------------------------------------------------------------------------- #
# Time series
# --------------------------------------------------------------------------- #
def _normalize_dates(df_index: object) -> list[date]:
    """Return a list of python date objects from a tz-aware DatetimeIndex."""
    out: list[date] = []
    for ts in df_index:
        if isinstance(ts, datetime):
            out.append(ts.date())
        else:
            out.append(ts)
    return out


def fetch_candles(symbol: str, start: date | None = None) -> list[dict]:
    """Fetch daily OHLCV. If start is None, fetch full history (period=max).

    Args:
        symbol: Yahoo Finance ticker symbol.
        start: Start date for fetch. None means full history.

    Returns:
        List of candle dicts with keys: ticker, trade_date, open, high, low,
        close, adj_close, volume.
    """
    tkr = yf.Ticker(symbol)
    try:
        if start is None:
            hist = tkr.history(period="max", auto_adjust=False)
        else:
            hist = tkr.history(start=start.isoformat(), auto_adjust=False)
    except Exception:
        return []
    if hist is None or len(hist) == 0:
        return []

    rows: list[dict] = []
    dates = _normalize_dates(hist.index)
    for i, d in enumerate(dates):
        r = hist.iloc[i]
        rows.append(
            {
                "ticker": symbol.upper(),
                "trade_date": d,
                "open": float(r["Open"]) if r["Open"] == r["Open"] else None,
                "high": float(r["High"]) if r["High"] == r["High"] else None,
                "low": float(r["Low"]) if r["Low"] == r["Low"] else None,
                "close": float(r["Close"]) if r["Close"] == r["Close"] else None,
                "adj_close": float(r["Adj Close"]) if r["Adj Close"] == r["Adj Close"] else None,
                "volume": int(r["Volume"]) if r["Volume"] == r["Volume"] else None,
            }
        )
    return rows


def fetch_dividends(symbol: str, start: date | None = None) -> list[dict]:
    """Fetch dividend history for a ticker.

    Args:
        symbol: Yahoo Finance ticker symbol.
        start: Only return dividends after this date.

    Returns:
        List of dividend dicts with keys: ticker, pay_date, amount.
    """
    try:
        ser = yf.Ticker(symbol).dividends
    except Exception:
        return []
    if ser is None:
        return []
    rows: list[dict] = []
    for ts, amount in ser.items():
        d = ts.date() if isinstance(ts, datetime) else ts
        if start and d <= start:
            continue
        rows.append({"ticker": symbol.upper(), "pay_date": d, "amount": float(amount)})
    return rows


def fetch_splits(symbol: str, start: date | None = None) -> list[dict]:
    """Fetch split history for a ticker.

    Args:
        symbol: Yahoo Finance ticker symbol.
        start: Only return splits after this date.

    Returns:
        List of split dicts with keys: ticker, split_date, ratio.
    """
    try:
        ser = yf.Ticker(symbol).splits
    except Exception:
        return []
    if ser is None:
        return []
    rows: list[dict] = []
    for ts, ratio in ser.items():
        d = ts.date() if isinstance(ts, datetime) else ts
        if start and d <= start:
            continue
        rows.append({"ticker": symbol.upper(), "split_date": d, "ratio": float(ratio)})
    return rows


# --------------------------------------------------------------------------- #
# Smart sync (one ticker)
# --------------------------------------------------------------------------- #
def sync_ticker(
    conn: object,
    symbol: str,
    force_full: bool = False,
    resume_from: date | None = None,
) -> dict:
    """Upsert metadata + all time series for one ticker.

    Smart sync: resume from resume_from (explicit), else the day after the last
    stored trade_date, else full history.

    Args:
        conn: Active database connection.
        symbol: Yahoo Finance ticker symbol.
        force_full: If True, ignore resume point and fetch full history.
        resume_from: Explicit resume date (day after this date is fetched).

    Returns:
        Dict with keys: ticker, candles, dividends, splits, from,
        last_candle_date.

    Raises:
        RuntimeError: If ticker is unavailable or has zero data on initial sync.
    """
    symbol = symbol.upper()
    today = date.today()

    meta = fetch_ticker_meta(symbol)
    if meta is None:
        raise RuntimeError(
            f"metadata unavailable for {symbol} (possibly delisted / not found)"
        )

    if resume_from is not None:
        last = resume_from
    elif force_full:
        last = None
    else:
        last = max_candle_date(conn, symbol)
    start = (last + timedelta(days=1)) if last else None

    logger.info("Fetching data for %s (start=%s)", symbol, start or "max")

    candles = fetch_candles(symbol, start)
    divs = fetch_dividends(symbol, start)
    splits = fetch_splits(symbol, start)

    if start is None and not candles and not divs and not splits:
        raise RuntimeError(f"no market data returned for {symbol} (skipped)")

    upsert_ticker(conn, meta)
    for row in candles:
        upsert_candle(conn, row)

    for row in divs:
        upsert_dividend(conn, row)

    for row in splits:
        upsert_split(conn, row)

    new_last = candles[-1]["trade_date"] if candles else last
    upsert_sync(conn, symbol, today, new_last)

    logger.info(
        "Sync complete for %s: %d candles, %d dividends, %d splits (from %s)",
        symbol, len(candles), len(divs), len(splits), start or "max",
    )

    return {
        "ticker": symbol,
        "candles": len(candles),
        "dividends": len(divs),
        "splits": len(splits),
        "from": start.isoformat() if start else "max",
        "last_candle_date": new_last.isoformat() if new_last else None,
    }
