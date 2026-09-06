"""Portfolio exposure calculations.

Computes sector and industry exposure from portfolio weights.
All functions accept a psycopg Connection — no global state.
"""
from __future__ import annotations

import logging

import psycopg

from shared.db import get_portfolio as _get_portfolio, get_portfolio_securities

logger = logging.getLogger(__name__)


def portfolio_sector_exposure(conn: psycopg.Connection, portfolio_id: int) -> list[dict]:
    """Compute sector exposure for a portfolio.

    Groups securities by sector and sums their weights.

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.

    Returns:
        List of dicts sorted by weight descending:
        [{"sector": "Technology", "weight": 0.45, "tickers": ["AAPL", "MSFT"]}, ...]

    Raises:
        ValueError: If portfolio not found.
    """
    portfolio = _get_portfolio(conn, portfolio_id)
    if portfolio is None:
        raise ValueError(f"Portfolio id {portfolio_id} not found")

    securities = get_portfolio_securities(conn, portfolio_id)

    sector_map: dict[str, dict] = {}
    for sec in securities:
        sector = sec["sector"] or "Unknown"
        if sector not in sector_map:
            sector_map[sector] = {"sector": sector, "weight": 0.0, "tickers": []}
        sector_map[sector]["weight"] += sec["weight"]
        sector_map[sector]["tickers"].append(sec["ticker"])

    result = sorted(sector_map.values(), key=lambda x: x["weight"], reverse=True)
    logger.info(
        "Sector exposure for portfolio '%s': %d sectors",
        portfolio["name"], len(result),
    )
    return result


def portfolio_industry_exposure(conn: psycopg.Connection, portfolio_id: int) -> list[dict]:
    """Compute industry exposure for a portfolio.

    Groups securities by industry and sums their weights.

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.

    Returns:
        List of dicts sorted by weight descending:
        [{"industry": "Semiconductors", "weight": 0.30, "tickers": ["NVDA"]}, ...]

    Raises:
        ValueError: If portfolio not found.
    """
    portfolio = _get_portfolio(conn, portfolio_id)
    if portfolio is None:
        raise ValueError(f"Portfolio id {portfolio_id} not found")

    securities = get_portfolio_securities(conn, portfolio_id)

    industry_map: dict[str, dict] = {}
    for sec in securities:
        industry = sec["industry"] or "Unknown"
        if industry not in industry_map:
            industry_map[industry] = {"industry": industry, "weight": 0.0, "tickers": []}
        industry_map[industry]["weight"] += sec["weight"]
        industry_map[industry]["tickers"].append(sec["ticker"])

    result = sorted(industry_map.values(), key=lambda x: x["weight"], reverse=True)
    logger.info(
        "Industry exposure for portfolio '%s': %d industries",
        portfolio["name"], len(result),
    )
    return result


def portfolio_exposure(conn: psycopg.Connection, portfolio_id: int) -> dict:
    """Compute both sector and industry exposure for a portfolio.

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.

    Returns:
        Dict with "sector" and "industry" keys, each holding a list of exposure dicts.
    """
    return {
        "sector": portfolio_sector_exposure(conn, portfolio_id),
        "industry": portfolio_industry_exposure(conn, portfolio_id),
    }
