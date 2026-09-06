"""Interactive market-data ingestion CLI.

Usage:
    python -m cli.main [--LOG DEBUG|INFO|WARNING|ERROR]

Menu (runs indefinitely until 'exit'):
    update          sync every ticker in config/tickers.csv with latest data
    add SYMBOL      add SYMBOL to the roster (only if tradable on yfinance)
    list            show current roster + sync state
    exit            quit

Every task logs what it is doing now, and on completion reports elapsed time
and the number of rows manipulated.
"""
from __future__ import annotations

import argparse
import logging
import time
from contextlib import contextmanager
from datetime import date

import yfinance as yf

from shared.config import load_db_config
from shared.db import get_connection
from shared.ingest import sync_ticker
from shared.logging_setup import setup_logging
from shared.roster import add_ticker_to_roster, read_roster, write_roster

log: logging.Logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
@contextmanager
def timed_task(action: str):
    """Log the start of a task, yield a stats dict, log time + counts at end."""
    log.info("==> START  %s", action)
    t0 = time.perf_counter()
    stats: dict = {}
    try:
        yield stats
    finally:
        dur = time.perf_counter() - t0
        parts = ", ".join(f"{k}={v}" for k, v in stats.items())
        log.info("<== FINISH %s  elapsed=%.2fs  %s", action, dur, parts)


def is_tradable(symbol: str) -> bool:
    """Check if a symbol is available on yfinance."""
    try:
        t = yf.Ticker(symbol)
        info = t.info
        if info and (
            info.get("regularMarketPrice") is not None
            or info.get("shortName") is not None
            or info.get("quoteType") is not None
        ):
            return True
        # info can be empty for some valid symbols; fall back to history
        return not t.history(period="1d").empty
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Menu actions
# --------------------------------------------------------------------------- #
def do_update(conn: object) -> None:
    """Sync all tickers in the roster with latest data."""
    rows = read_roster()
    if not rows:
        log.warning("Roster is empty. Use 'add SYMBOL' first.")
        return

    totals: dict = {"tickers": 0, "candles": 0, "dividends": 0, "splits": 0}
    failed: list[str] = []
    with timed_task(f"update all ({len(rows)} tickers)") as stats:
        today = date.today()
        for r in rows:
            sym = r["ticker"]
            log.info("-- syncing %s (resume_from=%s)", sym, r["last_candle_date"])
            try:
                s = sync_ticker(conn, sym, resume_from=r["last_candle_date"])
            except Exception as exc:
                conn.rollback()  # type: ignore[union-attr]
                failed.append(sym)
                log.error("   %s: SKIPPED (%s)", sym, exc)
                continue
            conn.commit()  # type: ignore[union-attr]
            r["last_synced_on"] = today
            lcd = s["last_candle_date"]
            r["last_candle_date"] = date.fromisoformat(lcd) if lcd else None
            totals["tickers"] += 1
            totals["candles"] += s["candles"]
            totals["dividends"] += s["dividends"]
            totals["splits"] += s["splits"]
            log.info(
                "   %s: +%d candles, +%d div, +%d splits (from %s)",
                sym, s["candles"], s["dividends"], s["splits"], s["from"],
            )
        write_roster(rows)
        stats.update(totals)
        if failed:
            stats["failed"] = len(failed)
            log.warning("Skipped %d ticker(s): %s", len(failed), ", ".join(failed))


def do_add(conn: object, symbol: str) -> None:
    """Add a new ticker to the roster and perform initial full sync."""
    symbol = symbol.upper().strip()
    if not symbol:
        log.error("No symbol provided. Usage: add SYMBOL")
        return
    with timed_task(f"add {symbol}") as stats:
        if not is_tradable(symbol):
            log.error("%s is not available on yfinance — not added.", symbol)
            stats["added"] = False
            return
        added = add_ticker_to_roster(symbol)
        if not added:
            log.warning("%s already in roster.", symbol)
        else:
            log.info("%s added to roster; performing initial full sync.", symbol)
            s = sync_ticker(conn, symbol, force_full=True)
            today = date.today()
            lcd = s["last_candle_date"]
            rows = read_roster()
            for r in rows:
                if r["ticker"] == symbol:
                    r["last_synced_on"] = today
                    r["last_candle_date"] = date.fromisoformat(lcd) if lcd else None
            write_roster(rows)
            stats.update({"added": True, **s})


def do_list() -> None:
    """Display the current roster with sync state."""
    rows = read_roster()
    if not rows:
        log.info("Roster empty.")
        return
    log.info("%-12s %-12s %-12s", "TICKER", "LAST_SYNCED", "LAST_CANDLE")
    for r in rows:
        log.info(
            "%-12s %-12s %-12s",
            r["ticker"],
            str(r["last_synced_on"] or "-"),
            str(r["last_candle_date"] or "-"),
        )


MENU = """\033[1;34m
=== r9_analytics ingestion ===
  update        sync all tickers with latest data
  add SYMBOL    add a new ticker to the roster
  list          show roster + sync state
  exit          quit
\033[0m"""


def main() -> None:
    """Entry point for the interactive CLI."""
    ap = argparse.ArgumentParser(description="r9_analytics market ingestion")
    ap.add_argument(
        "--LOG",
        default="DEBUG",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="log level (default DEBUG)",
    )
    args = ap.parse_args()

    global log
    log = setup_logging(args.LOG)

    cfg = load_db_config()
    log.info("Loaded DB config for %s@%s:%s", cfg["dbname"], cfg["host"], cfg["port"])

    while True:
        print(MENU)
        try:
            choice = input("\033[1;36mr9>\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            log.info("Interrupted — exiting.")
            break

        if choice in ("exit", "quit", "q"):
            log.info("Goodbye.")
            break
        elif choice == "update":
            with get_connection(cfg) as conn:
                do_update(conn)
        elif choice.startswith("add"):
            sym = choice[len("add"):].strip()
            with get_connection(cfg) as conn:
                do_add(conn, sym)
        elif choice == "list":
            do_list()
        elif choice == "":
            continue
        else:
            log.warning(
                "Unknown command: %r. Try update / add SYMBOL / list / exit.",
                choice,
            )


if __name__ == "__main__":
    main()
