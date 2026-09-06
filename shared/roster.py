"""Roster handling for config/tickers.csv.

CSV columns: ticker, last_synced_on, last_candle_date
This file is the authoritative list of tickers to track and carries the
smart-sync hints (last_candle_date) used on subsequent runs.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from shared.config import ROSTER_PATH

logger = logging.getLogger(__name__)


def _parse_date(v: str) -> date | None:
    """Parse an ISO date string, returning None for empty/blank values."""
    v = (v or "").strip()
    if not v:
        return None
    return date.fromisoformat(v)


def read_roster(path: Path | None = None) -> list[dict]:
    """Read the ticker roster from CSV.

    Args:
        path: Path to CSV file. Defaults to config/tickers.csv.

    Returns:
        List of dicts with keys: ticker, last_synced_on, last_candle_date.
    """
    roster_path = path or ROSTER_PATH
    rows: list[dict] = []
    if not roster_path.exists():
        logger.warning("Roster file not found: %s", roster_path)
        return rows
    with open(roster_path, "r", newline="") as fh:
        header = fh.readline()  # skip header
        for line in fh:
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            ticker = parts[0]
            rows.append(
                {
                    "ticker": ticker,
                    "last_synced_on": _parse_date(parts[1]) if len(parts) > 1 else None,
                    "last_candle_date": _parse_date(parts[2]) if len(parts) > 2 else None,
                }
            )
    logger.debug("Loaded %d tickers from roster", len(rows))
    return rows


def write_roster(rows: list[dict], path: Path | None = None) -> None:
    """Write the ticker roster back to CSV.

    Args:
        rows: List of roster dicts to write.
        path: Path to CSV file. Defaults to config/tickers.csv.
    """
    roster_path = path or ROSTER_PATH
    with open(roster_path, "w", newline="") as fh:
        fh.write("ticker,last_synced_on,last_candle_date\n")
        for r in rows:
            lso = r.get("last_synced_on")
            lcd = r.get("last_candle_date")
            fh.write(
                f"{r['ticker']},"
                f"{lso.isoformat() if lso else ''},"
                f"{lcd.isoformat() if lcd else ''}\n"
            )
    logger.debug("Wrote %d tickers to roster", len(rows))


def add_ticker_to_roster(ticker: str, path: Path | None = None) -> bool:
    """Append ticker with empty sync dates if not already present.

    Args:
        ticker: Symbol to add (will be uppercased).
        path: Path to CSV file. Defaults to config/tickers.csv.

    Returns:
        True if added, False if already present.
    """
    ticker = ticker.upper()
    roster_path = path or ROSTER_PATH
    rows = read_roster(roster_path)
    if any(r["ticker"] == ticker for r in rows):
        logger.info("Ticker %s already in roster", ticker)
        return False
    rows.append({"ticker": ticker, "last_synced_on": None, "last_candle_date": None})
    write_roster(rows, roster_path)
    logger.info("Added %s to roster", ticker)
    return True
