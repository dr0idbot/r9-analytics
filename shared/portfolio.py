"""Portfolio business logic.

Manages portfolio creation, security management, and weight validation.
All functions accept a psycopg Connection — no global state.
"""
from __future__ import annotations

import logging

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

WEIGHT_TOLERANCE = 0.001  # sum of weights must be within ±0.001 of 1.0


class PortfolioError(Exception):
    """Base exception for portfolio operations."""


class CurrencyMismatchError(PortfolioError):
    """Raised when a security's currency doesn't match the portfolio's currency."""


class WeightSumError(PortfolioError):
    """Raised when weights don't sum to 1.0 within tolerance."""


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


def _validate_weight_sum(weights: dict[str, float]) -> None:
    """Validate that weights sum to 1.0 within tolerance."""
    total = sum(weights.values())
    if abs(total - 1.0) > WEIGHT_TOLERANCE:
        raise WeightSumError(
            f"Weights must sum to 1.0 (±{WEIGHT_TOLERANCE}), got {total:.4f}"
        )


def create_portfolio(conn: psycopg.Connection, name: str, currency: str) -> int:
    """Create a new portfolio.

    Args:
        conn: Database connection.
        name: Portfolio name (must be unique).
        currency: ISO currency code (e.g. "USD"). Locked at creation.

    Returns:
        The new portfolio id.

    Raises:
        psycopg.IntegrityError: If name already exists.
    """
    portfolio_id = _insert_portfolio(conn, name, currency.upper())
    logger.info("Created portfolio '%s' (id=%d, currency=%s)", name, portfolio_id, currency)
    return portfolio_id


def add_security(
    conn: psycopg.Connection, portfolio_id: int, ticker: str, weight: float
) -> None:
    """Add or update a security in a portfolio.

    Validates:
    - Ticker exists in tickers table
    - Ticker currency matches portfolio currency
    - Weight is between 0 and 1

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.
        ticker: Ticker symbol.
        weight: Weight as decimal (0.0 to 1.0).

    Raises:
        TickerNotFoundError: If ticker doesn't exist.
        CurrencyMismatchError: If currency doesn't match.
        PortfolioError: If weight is out of range.
    """
    portfolio = _get_portfolio(conn, portfolio_id)
    if portfolio is None:
        raise PortfolioError(f"Portfolio id {portfolio_id} not found")

    if weight < 0 or weight > 1:
        raise PortfolioError(f"Weight must be between 0 and 1, got {weight}")

    _validate_currency_match(conn, portfolio["currency"], ticker)
    upsert_portfolio_security(conn, portfolio_id, ticker.upper(), weight)
    logger.info(
        "Added %s to portfolio '%s' (weight=%.4f)",
        ticker, portfolio["name"], weight,
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


def set_weights(conn: psycopg.Connection, portfolio_id: int, weights: dict[str, float]) -> None:
    """Bulk update weights for a portfolio.

    Validates that weights sum to 1.0 (±0.001).

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.
        weights: Dict of {ticker: weight}.

    Raises:
        WeightSumError: If weights don't sum to 1.0.
        CurrencyMismatchError: If any ticker currency doesn't match.
    """
    portfolio = _get_portfolio(conn, portfolio_id)
    if portfolio is None:
        raise PortfolioError(f"Portfolio id {portfolio_id} not found")

    _validate_weight_sum(weights)

    for ticker, weight in weights.items():
        _validate_currency_match(conn, portfolio["currency"], ticker)
        upsert_portfolio_security(conn, portfolio_id, ticker.upper(), weight)

    logger.info(
        "Set weights for portfolio '%s': %s",
        portfolio["name"], weights,
    )


def get_portfolio_detail(conn: psycopg.Connection, portfolio_id: int) -> dict | None:
    """Return portfolio metadata with its securities.

    Returns:
        Dict with portfolio info and securities list, or None if not found.
    """
    portfolio = _get_portfolio(conn, portfolio_id)
    if portfolio is None:
        return None

    securities = get_portfolio_securities(conn, portfolio_id)
    portfolio["securities"] = securities
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
