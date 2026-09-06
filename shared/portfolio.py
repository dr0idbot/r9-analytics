"""Portfolio business logic.

Manages portfolio creation, security management, and weight validation.
All functions accept a psycopg Connection — no global state.
"""
from __future__ import annotations

import logging
from datetime import date

import psycopg

from shared.db import (
    delete_portfolio as _delete_portfolio,
    delete_portfolio_security,
    get_portfolio as _get_portfolio,
    get_portfolio_securities,
    get_ticker_currency,
    insert_portfolio as _insert_portfolio,
    list_portfolios as _list_portfolios,
    upsert_portfolio_security,
)

logger = logging.getLogger(__name__)


class PortfolioError(Exception):
    """Base exception for portfolio operations."""


class CurrencyMismatchError(PortfolioError):
    """Raised when a security's currency doesn't match the portfolio's currency."""


class TickerNotFoundError(PortfolioError):
    """Raised when a ticker doesn't exist in the tickers table."""


def _validate_currency_match(conn: psycopg.Connection, portfolio_currency: str, ticker: str) -> None:
    """Validate that a ticker's currency matches the portfolio's currency."""
    ticker_currency = get_ticker_currency(conn, ticker)
    if ticker_currency is None:
        raise TickerNotFoundError(f"Ticker '{ticker}' not found in tickers table")
    if ticker_currency.upper() != portfolio_currency.upper():
        raise CurrencyMismatchError(
            f"Ticker '{ticker}' is {ticker_currency}, "
            f"but portfolio requires {portfolio_currency}"
        )


def create_portfolio(conn: psycopg.Connection, name: str, currency: str) -> int:
    """Create a new portfolio.

    Args:
        conn: Database connection.
        name: Portfolio name (must be unique).
        currency: ISO currency code (e.g. "USD"). Locked at creation.

    Returns:
        The new portfolio id.
    """
    portfolio_id = _insert_portfolio(conn, name, currency.upper())
    logger.info("Created portfolio '%s' (id=%d, currency=%s)", name, portfolio_id, currency)
    return portfolio_id


def add_security(
    conn: psycopg.Connection, portfolio_id: int, ticker: str,
    buy_price: float, buy_date: date, units: float
) -> None:
    """Add or update a security in a portfolio.

    Validates:
    - Ticker exists in tickers table
    - Ticker currency matches portfolio currency
    - buy_price and units are positive

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.
        ticker: Ticker symbol.
        buy_price: Price per unit at purchase.
        buy_date: Date of purchase.
        units: Number of units/shares.

    Raises:
        TickerNotFoundError: If ticker doesn't exist.
        CurrencyMismatchError: If currency doesn't match.
        PortfolioError: If buy_price or units are invalid.
    """
    portfolio = _get_portfolio(conn, portfolio_id)
    if portfolio is None:
        raise PortfolioError(f"Portfolio id {portfolio_id} not found")

    if buy_price <= 0:
        raise PortfolioError(f"buy_price must be positive, got {buy_price}")
    if units <= 0:
        raise PortfolioError(f"units must be positive, got {units}")

    _validate_currency_match(conn, portfolio["currency"], ticker)
    upsert_portfolio_security(conn, portfolio_id, ticker.upper(), buy_price, buy_date, units)
    logger.info(
        "Added %s to portfolio '%s' (buy_price=%.2f, units=%.4f)",
        ticker, portfolio["name"], buy_price, units,
    )


def remove_security(conn: psycopg.Connection, portfolio_id: int, ticker: str) -> None:
    """Remove a security from a portfolio.

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.
        ticker: Ticker symbol.
    """
    delete_portfolio_security(conn, portfolio_id, ticker.upper())
    logger.info("Removed %s from portfolio id=%d", ticker, portfolio_id)


def get_portfolio_detail(conn: psycopg.Connection, portfolio_id: int) -> dict | None:
    """Return portfolio metadata with its securities.

    Returns:
        Dict with portfolio info and securities list, or None if not found.
    """
    portfolio = _get_portfolio(conn, portfolio_id)
    if portfolio is None:
        return None

    securities = get_portfolio_securities(conn, portfolio_id)

    # Calculate total value and weights
    total_value = sum(s["buy_price"] * s["units"] for s in securities)
    for sec in securities:
        sec["market_value"] = sec["buy_price"] * sec["units"]
        sec["weight"] = sec["market_value"] / total_value if total_value > 0 else 0

    portfolio["securities"] = securities
    portfolio["total_value"] = total_value
    portfolio["total_weight"] = sum(s["weight"] for s in securities)
    return portfolio


def list_portfolios(conn: psycopg.Connection) -> list[dict]:
    """Return all portfolios with security count."""
    return _list_portfolios(conn)


def delete_portfolio(conn: psycopg.Connection, portfolio_id: int) -> None:
    """Delete a portfolio and all its securities.

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.
    """
    _delete_portfolio(conn, portfolio_id)
    logger.info("Deleted portfolio id=%d", portfolio_id)
