"""Roster handling for config/tickers.csv.

CSV columns: ticker, last_synced_on, last_candle_date
This file is the authoritative list of tickers to track and carries the
smart-sync hints (last_candle_date) used on subsequent runs.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

ROSTER_PATH = Path(__file__).resolve().parent.parent / "config" / "tickers.csv"


def _parse_date(v: str) -> Optional[date]:
    v = (v or "").strip()
    if not v:
        return None
    return date.fromisoformat(v)


def read_roster(path: Path = ROSTER_PATH) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with open(path, "r", newline="") as fh:
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
    return rows


def write_roster(rows: list[dict], path: Path = ROSTER_PATH) -> None:
    with open(path, "w", newline="") as fh:
        fh.write("ticker,last_synced_on,last_candle_date\n")
        for r in rows:
            lso = r.get("last_synced_on")
            lcd = r.get("last_candle_date")
            fh.write(
                f"{r['ticker']},"
                f"{lso.isoformat() if lso else ''},"
                f"{lcd.isoformat() if lcd else ''}\n"
            )


def add_ticker_to_roster(ticker: str, path: Path = ROSTER_PATH) -> bool:
    """Append ticker with empty sync dates if not already present. Returns True if added."""
    ticker = ticker.upper()
    rows = read_roster(path)
    if any(r["ticker"] == ticker for r in rows):
        return False
    rows.append({"ticker": ticker, "last_synced_on": None, "last_candle_date": None})
    write_roster(rows, path)
    return True
