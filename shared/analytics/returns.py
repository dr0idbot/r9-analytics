"""Canonical return engine.

One authoritative implementation for computing returns.
All performance/risk calculations must use these functions.
"""
from __future__ import annotations

import logging
from datetime import date

import numpy as np
import pandas as pd

from shared.models import AnalysisContext, MetricResult

logger = logging.getLogger(__name__)


def price_returns(prices: pd.Series) -> pd.Series:
    """Compute simple price returns from a price series.

    Args:
        prices: Price series sorted by date (ascending).

    Returns:
        Simple returns: (P_t / P_{t-1}) - 1.
        First observation is NaN.
    """
    if prices.empty or len(prices) < 2:
        return pd.Series(dtype=float, name="returns")
    return prices.pct_change()


def total_returns(adjusted_prices: pd.Series) -> pd.Series:
    """Compute total returns from adjusted price series.

    Adjusted prices account for dividends, splits, and other corporate actions.
    This is the recommended methodology for investment performance.

    Args:
        adjusted_prices: Adjusted close price series sorted by date (ascending).

    Returns:
        Total returns: (Adj_P_t / Adj_P_{t-1}) - 1.
        First observation is NaN.
    """
    if adjusted_prices.empty or len(adjusted_prices) < 2:
        return pd.Series(dtype=float, name="returns")
    return adjusted_prices.pct_change()


def log_returns(prices: pd.Series) -> pd.Series:
    """Compute continuously compounded (log) returns.

    Args:
        prices: Price series sorted by date (ascending).

    Returns:
        Log returns: ln(P_t / P_{t-1}).
        First observation is NaN.
    """
    if prices.empty or len(prices) < 2:
        return pd.Series(dtype=float, name="log_returns")
    return np.log(prices / prices.shift(1))


def cumulative_return(returns: pd.Series) -> pd.Series:
    """Compute cumulative return from a return series.

    Args:
        returns: Return series.

    Returns:
        Cumulative return series: (1 + r_1) * (1 + r_2) * ... - 1.
    """
    if returns.empty:
        return pd.Series(dtype=float, name="cumulative_return")
    return (1 + returns).cumprod() - 1


def annualized_return(
    returns: pd.Series,
    periods_per_year: int = 252,
) -> float | None:
    """Compute annualized return from a return series.

    Uses geometric (compound) annualization.

    Args:
        returns: Return series (daily, weekly, etc.).
        periods_per_year: Number of return periods in a year.

    Returns:
        Annualized return as decimal, or None if insufficient data.
    """
    clean = returns.dropna()
    if len(clean) < 2:
        return None

    total = (1 + clean).prod()
    n_periods = len(clean)
    annualized = total ** (periods_per_year / n_periods) - 1
    return float(annualized)


def annualized_volatility(
    returns: pd.Series,
    periods_per_year: int = 252,
    ddof: int = 1,
) -> float | None:
    """Compute annualized volatility from a return series.

    Args:
        returns: Return series.
        periods_per_year: Number of return periods in a year.
        ddof: Degrees of freedom (1 for sample, 0 for population).

    Returns:
        Annualized volatility as decimal, or None if insufficient data.
    """
    clean = returns.dropna()
    if len(clean) < 2:
        return None

    daily_vol = clean.std(ddof=ddof)
    return float(daily_vol * np.sqrt(periods_per_year))


def _validate_returns(
    returns: pd.Series,
    ctx: AnalysisContext,
    metric_name: str,
) -> MetricResult | None:
    """Validate returns and return MetricResult if insufficient.

    Returns None if returns are valid, or a MetricResult with status
    indicating the problem.
    """
    clean = returns.dropna()
    if len(clean) < ctx.min_observations:
        return MetricResult(
            name=metric_name,
            value=None,
            status="insufficient_data",
            observations=len(clean),
            frequency=ctx.frequency,
            return_type=ctx.return_type,
            methodology=f"Requires at least {ctx.min_observations} observations",
            warnings=[f"Only {len(clean)} observations available"],
        )
    return None
