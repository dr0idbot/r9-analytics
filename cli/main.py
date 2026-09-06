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
from shared.db import get_connection, list_currencies
from shared.ingest import sync_ticker
from shared.logging_setup import setup_logging
from shared.portfolio import (
    PortfolioError,
    add_security,
    create_portfolio,
    delete_portfolio,
    get_portfolio_detail,
    list_portfolios,
    remove_security,
)
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


# --------------------------------------------------------------------------- #
# Portfolio actions
# --------------------------------------------------------------------------- #
def do_portfolio_list(conn: object) -> None:
    """List all portfolios."""
    portfolios = list_portfolios(conn)
    if not portfolios:
        log.info("No portfolios. Use 'pn' to create one.")
        return
    log.info("%-5s %-25s %-8s %-12s", "ID", "NAME", "CURRENCY", "SECURITIES")
    for p in portfolios:
        log.info(
            "%-5d %-25s %-8s %-12d",
            p["id"], p["name"], p["currency"], p["security_count"],
        )


def do_portfolio_new(conn: object) -> None:
    """Create a new portfolio."""
    name = input("  Portfolio name: ").strip()
    if not name:
        log.error("Name cannot be empty.")
        return

    currencies = list_currencies(conn)
    log.info("Available currencies: %s", ", ".join(currencies))
    currency = input("  Currency: ").strip().upper()
    if currency not in currencies:
        log.error("Invalid currency. Choose from: %s", ", ".join(currencies))
        return

    try:
        pid = create_portfolio(conn, name, currency)
        log.info("Created portfolio '%s' (id=%d, currency=%s)", name, pid, currency)
    except Exception as e:
        log.error("Failed to create portfolio: %s", e)


def do_portfolio_add(conn: object) -> None:
    """Add a security to a portfolio."""
    from datetime import date as date_type

    portfolios = list_portfolios(conn)
    if not portfolios:
        log.info("No portfolios. Use 'pn' to create one.")
        return

    log.info("Available portfolios:")
    for p in portfolios:
        log.info("  %d: %s (%s, %d securities)", p["id"], p["name"], p["currency"], p["security_count"])

    try:
        pid = int(input("  Portfolio ID: ").strip())
    except ValueError:
        log.error("Invalid ID.")
        return

    ticker = input("  Ticker symbol: ").strip().upper()
    if not ticker:
        log.error("Ticker cannot be empty.")
        return

    try:
        buy_price = float(input("  Buy price per unit: ").strip())
    except ValueError:
        log.error("Invalid buy price.")
        return

    date_str = input("  Buy date (YYYY-MM-DD): ").strip()
    try:
        buy_date = date_type.fromisoformat(date_str)
    except ValueError:
        log.error("Invalid date format. Use YYYY-MM-DD.")
        return

    try:
        units = int(input("  Number of units: ").strip())
    except ValueError:
        log.error("Invalid units. Must be an integer.")
        return

    try:
        add_security(conn, pid, ticker, buy_price, buy_date, units)
        log.info(
            "Added %s to portfolio id=%d (price=%.2f, units=%d)",
            ticker, pid, buy_price, units,
        )
    except PortfolioError as e:
        log.error("Failed: %s", e)


def do_portfolio_remove(conn: object) -> None:
    """Remove a security from a portfolio."""
    portfolios = list_portfolios(conn)
    if not portfolios:
        log.info("No portfolios.")
        return

    log.info("Available portfolios:")
    for p in portfolios:
        log.info("  %d: %s (%s, %d securities)", p["id"], p["name"], p["currency"], p["security_count"])

    try:
        pid = int(input("  Portfolio ID: ").strip())
    except ValueError:
        log.error("Invalid ID.")
        return

    detail = get_portfolio_detail(conn, pid)
    if detail is None:
        log.error("Portfolio not found.")
        return

    if not detail["securities"]:
        log.info("Portfolio has no securities.")
        return

    log.info("Securities in '%s':", detail["name"])
    for s in detail["securities"]:
        log.info(
            "  %s (buy_price=%.2f, units=%.4f, weight=%.2f%%, sector=%s)",
            s["ticker"], s["buy_price"], s["units"], s["weight"] * 100, s["sector"],
        )

    ticker = input("  Ticker to remove: ").strip().upper()
    remove_security(conn, pid, ticker)
    log.info("Removed %s from portfolio id=%d", ticker, pid)


def do_portfolio_delete(conn: object) -> None:
    """Delete a portfolio."""
    portfolios = list_portfolios(conn)
    if not portfolios:
        log.info("No portfolios.")
        return

    log.info("Available portfolios:")
    for p in portfolios:
        log.info("  %d: %s (%s, %d securities)", p["id"], p["name"], p["currency"], p["security_count"])

    try:
        pid = int(input("  Portfolio ID to delete: ").strip())
    except ValueError:
        log.error("Invalid ID.")
        return

    detail = get_portfolio_detail(conn, pid)
    if detail is None:
        log.error("Portfolio not found.")
        return

    confirm = input(f"  Delete '{detail['name']}'? (yes/no): ").strip().lower()
    if confirm != "yes":
        log.info("Cancelled.")
        return

    delete_portfolio(conn, pid)
    log.info("Deleted portfolio '%s'", detail["name"])


def do_risk(conn: object) -> None:
    """Show single-asset risk metrics for a ticker."""
    from shared.calculations import single_asset_risk

    ticker = input("  Ticker symbol: ").strip().upper()
    if not ticker:
        log.error("Ticker cannot be empty.")
        return

    risk = single_asset_risk(conn, ticker)

    log.info("\n=== Risk Metrics: %s ===", risk["ticker"])
    log.info("  Realized Volatility:    %8.2f%%", risk["realized_volatility"] * 100)
    log.info("  Parkinson Volatility:   %8.2f%%", risk["parkinson_volatility"] * 100)
    log.info("  Garman-Klass Volatility:%8.2f%%", risk["garman_klass_volatility"] * 100)
    log.info("  Semi-Deviation:         %8.2f%%", risk["semi_deviation"] * 100)
    log.info("  Downside Ratio:         %8.4f", risk["downside_ratio"])
    log.info("  Max Drawdown:           %8.2f%%", risk["max_drawdown"] * 100)
    log.info("  Historical VaR (95%%):   %8.2f%%", risk["historical_var_95"] * 100)
    log.info("  Parametric VaR (95%%):   %8.2f%%", risk["parametric_var_95"] * 100)
    log.info("  CVaR (95%%):             %8.2f%%", risk["cvar_95"] * 100)


def do_portfolio_exposure(conn: object) -> None:
    """Show portfolio exposure."""
    from shared.calculations import portfolio_exposure

    portfolios = list_portfolios(conn)
    if not portfolios:
        log.info("No portfolios.")
        return

    log.info("Available portfolios:")
    for p in portfolios:
        log.info("  %d: %s (%s, %d securities)", p["id"], p["name"], p["currency"], p["security_count"])

    try:
        pid = int(input("  Portfolio ID: ").strip())
    except ValueError:
        log.error("Invalid ID.")
        return

    detail = get_portfolio_detail(conn, pid)
    if detail is None:
        log.error("Portfolio not found.")
        return

    exposure = portfolio_exposure(conn, pid)

    log.info("\n=== Portfolio: %s (%s) ===", detail["name"], detail["currency"])
    log.info("Securities: %d, Total weight: %.2f%%\n", len(detail["securities"]), detail["total_weight"] * 100)

    log.info("--- Sector Exposure ---")
    log.info("  %-30s %-10s %s", "SECTOR", "WEIGHT", "TICKERS")
    for s in exposure["sector"]:
        log.info("  %-30s %-10.2f%% %s", s["sector"], s["weight"] * 100, ", ".join(s["tickers"]))

    log.info("\n--- Industry Exposure ---")
    log.info("  %-30s %-10s %s", "INDUSTRY", "WEIGHT", "TICKERS")
    for ind in exposure["industry"]:
        log.info("  %-30s %-10.2f%% %s", ind["industry"], ind["weight"] * 100, ", ".join(ind["tickers"]))


MENU = """\033[1;34m
=== r9_analytics ingestion ===
  update        sync all tickers with latest data
  add SYMBOL    add a new ticker to the roster
  list          show roster + sync state

=== portfolios ===
  pl            list portfolios
  pn            create new portfolio
  pa            add security to portfolio
  pr            remove security from portfolio
  pd            delete portfolio
  px            show portfolio exposure

=== analytics ===
  risk          show single-asset risk metrics

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
        elif choice == "pl":
            with get_connection(cfg) as conn:
                do_portfolio_list(conn)
        elif choice == "pn":
            with get_connection(cfg) as conn:
                do_portfolio_new(conn)
        elif choice == "pa":
            with get_connection(cfg) as conn:
                do_portfolio_add(conn)
        elif choice == "pr":
            with get_connection(cfg) as conn:
                do_portfolio_remove(conn)
        elif choice == "pd":
            with get_connection(cfg) as conn:
                do_portfolio_delete(conn)
        elif choice == "px":
            with get_connection(cfg) as conn:
                do_portfolio_exposure(conn)
        elif choice == "risk":
            with get_connection(cfg) as conn:
                do_risk(conn)
        elif choice == "":
            continue
        else:
            log.warning(
                "Unknown command: %r. Try update / add SYMBOL / list / exit.",
                choice,
            )


if __name__ == "__main__":
    main()
