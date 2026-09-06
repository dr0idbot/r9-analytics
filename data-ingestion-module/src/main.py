"""Phase 4: Interactive market-data ingestion CLI.

Usage:
    python3 src/main.py [--LOG DEBUG|INFO|WARNING|ERROR]

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
import sys
import time
from contextlib import contextmanager
from datetime import date

import yfinance as yf

from db import get_connection, load_db_config
from ingest import sync_ticker
from logging_setup import setup_logging
from roster import add_ticker_to_roster, read_roster, write_roster

log = setup_logging("DEBUG")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
@contextmanager
def timed_task(action: str):
    """Log the start of a task, yield a stats dict, log time + counts at end."""
    log.info(f"==> START  {action}")
    t0 = time.perf_counter()
    stats: dict = {}
    try:
        yield stats
    finally:
        dur = time.perf_counter() - t0
        parts = ", ".join(f"{k}={v}" for k, v in stats.items())
        log.info(f"<== FINISH {action}  elapsed={dur:.2f}s  {parts}")


def is_tradable(symbol: str) -> bool:
    try:
        t = yf.Ticker(symbol)
        info = t.info
        if info and (info.get("regularMarketPrice") is not None
                     or info.get("shortName") is not None
                     or info.get("quoteType") is not None):
            return True
        # info can be empty for some valid symbols; fall back to history
        return not t.history(period="1d").empty
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Menu actions
# --------------------------------------------------------------------------- #
def do_update(conn) -> None:
    rows = read_roster()
    if not rows:
        log.warning("Roster is empty. Use 'add SYMBOL' first.")
        return

    totals = {"tickers": 0, "candles": 0, "dividends": 0, "splits": 0}
    failed = []
    with timed_task(f"update all ({len(rows)} tickers)") as stats:
        today = date.today()
        for r in rows:
            sym = r["ticker"]
            log.info(f"-- syncing {sym} (resume_from={r['last_candle_date']})")
            try:
                s = sync_ticker(conn, sym, resume_from=r["last_candle_date"])
            except Exception as exc:  # bad/delisted symbol: skip, keep going
                conn.rollback()  # discard this ticker's partial writes
                failed.append(sym)
                log.error(f"   {sym}: SKIPPED ({exc})")
                continue
            conn.commit()  # persist this ticker before moving on
            r["last_synced_on"] = today
            lcd = s["last_candle_date"]
            r["last_candle_date"] = date.fromisoformat(lcd) if lcd else None
            totals["tickers"] += 1
            totals["candles"] += s["candles"]
            totals["dividends"] += s["dividends"]
            totals["splits"] += s["splits"]
            log.info(f"   {sym}: +{s['candles']} candles, +{s['dividends']} "
                     f"div, +{s['splits']} splits (from {s['from']})")
        write_roster(rows)
        stats.update(totals)
        if failed:
            stats["failed"] = len(failed)
            log.warning(f"Skipped {len(failed)} ticker(s): {', '.join(failed)}")


def do_add(conn, symbol: str) -> None:
    symbol = symbol.upper().strip()
    if not symbol:
        log.error("No symbol provided. Usage: add SYMBOL")
        return
    with timed_task(f"add {symbol}") as stats:
        if not is_tradable(symbol):
            log.error(f"{symbol} is not available on yfinance — not added.")
            stats["added"] = False
            return
        added = add_ticker_to_roster(symbol)
        if not added:
            log.warning(f"{symbol} already in roster.")
        else:
            log.info(f"{symbol} added to roster; performing initial full sync.")
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
    rows = read_roster()
    if not rows:
        log.info("Roster empty.")
        return
    log.info(f"{'TICKER':<12} {'LAST_SYNCED':<12} {'LAST_CANDLE':<12}")
    for r in rows:
        log.info(f"{r['ticker']:<12} "
                 f"{str(r['last_synced_on'] or '-'):<12} "
                 f"{str(r['last_candle_date'] or '-'):<12}")


MENU = """\033[1;34m
=== r9_analytics ingestion ===
  update        sync all tickers with latest data
  add SYMBOL    add a new ticker to the roster
  list          show roster + sync state
  exit          quit
\033[0m"""


def main() -> None:
    ap = argparse.ArgumentParser(description="r9_analytics market ingestion")
    ap.add_argument("--LOG", default="DEBUG",
                    choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                    help="log level (default DEBUG)")
    args = ap.parse_args()

    global log
    log = setup_logging(args.LOG)

    cfg = load_db_config()
    log.info(f"Loaded DB config for {cfg['dbname']}@{cfg['host']}:{cfg['port']}")

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
            log.warning(f"Unknown command: {choice!r}. Try update / add SYMBOL / list / exit.")


if __name__ == "__main__":
    main()
