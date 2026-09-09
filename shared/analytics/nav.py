"""Historical portfolio NAV reconstruction.

Reconstructs time-series NAV from individual position histories.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """A position in a security with historical data.

    Attributes:
        ticker: Security ticker symbol.
        quantity: Number of shares held.
        buy_date: Date the position was opened.
        prices: Series of prices indexed by date (trade_date).
    """

    ticker: str
    quantity: float
    buy_date: date
    prices: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))


@dataclass
class NAVTimeSeries:
    """Portfolio NAV time series.

    Attributes:
        dates: Array of dates.
        nav: Array of NAV values.
        components: Dict mapping ticker to component NAV time series.
        weights: DataFrame of weights over time.
    """

    dates: np.ndarray
    nav: np.ndarray
    components: dict[str, np.ndarray]
    weights: pd.DataFrame


def build_historical_nav(positions: list[Position], start_date: date | None = None, end_date: date | None = None) -> NAVTimeSeries:
    """Build historical portfolio NAV from positions.

    For each position, the NAV starts from the buy_date.
    Before the buy_date, that position contributes 0 to the portfolio.

    Args:
        positions: List of Position objects with prices.
        start_date: Start date for the time series. If None, earliest common date.
        end_date: End date for the time series. If None, latest common date.

    Returns:
        NAVTimeSeries with dates, NAV, component contributions, and weights.
    """
    if not positions:
        return NAVTimeSeries(dates=np.array([]), nav=np.array([]), components={}, weights=pd.DataFrame())

    # Collect all dates across all positions
    all_dates: set[date] = set()
    for pos in positions:
        if not pos.prices.empty:
            all_dates.update(pos.prices.index)

    if not all_dates:
        return NAVTimeSeries(dates=np.array([]), nav=np.array([]), components={}, weights=pd.DataFrame())

    sorted_dates = sorted(all_dates)

    if start_date:
        sorted_dates = [d for d in sorted_dates if d >= start_date]
    if end_date:
        sorted_dates = [d for d in sorted_dates if d <= end_date]

    if not sorted_dates:
        return NAVTimeSeries(dates=np.array([]), nav=np.array([]), components={}, weights=pd.DataFrame())

    dates_array = np.array(sorted_dates)

    # Build component NAV series
    component_navs: dict[str, np.ndarray] = {}
    component_names: list[str] = []

    for pos in positions:
        component = np.full(len(sorted_dates), 0.0)
        for i, d in enumerate(sorted_dates):
            if d >= pos.buy_date and d in pos.prices.index:
                component[i] = pos.quantity * pos.prices.loc[d]
        component_navs[pos.ticker] = component
        component_names.append(pos.ticker)

    # Total NAV is sum of components
    nav = np.zeros(len(sorted_dates))
    for comp in component_navs.values():
        nav += comp

    # Build weights DataFrame
    weights_data = {}
    for ticker, comp in component_navs.items():
        with np.errstate(divide="ignore", invalid="ignore"):
            weights = np.where(nav > 0, comp / nav, 0.0)
        weights_data[ticker] = weights

    weights_df = pd.DataFrame(weights_data, index=dates_array)

    return NAVTimeSeries(
        dates=dates_array,
        nav=nav,
        components=component_navs,
        weights=weights_df,
    )


def nav_returns(nav_series: NAVTimeSeries) -> pd.Series:
    """Compute returns from NAV time series.

    Args:
        nav_series: NAVTimeSeries object.

    Returns:
        Series of returns indexed by date.
    """
    if len(nav_series.nav) < 2:
        return pd.Series(dtype=float)

    returns = np.diff(nav_series.nav) / nav_series.nav[:-1]
    return pd.Series(returns, index=nav_series.dates[1:])


def component_contributions(nav_series: NAVTimeSeries) -> pd.DataFrame:
    """Compute return contributions from each component.

    Args:
        nav_series: NAVTimeSeries object.

    Returns:
        DataFrame with dates as index, tickers as columns, values are return contributions.
    """
    if len(nav_series.nav) < 2:
        return pd.DataFrame()

    contributions = {}
    for ticker, comp in nav_series.components.items():
        if len(comp) < 2:
            continue
        comp_returns = np.diff(comp) / comp[:-1]
        with np.errstate(divide="ignore", invalid="ignore"):
            contributions[ticker] = np.where(
                nav_series.nav[:-1] > 0,
                comp_returns * (comp[:-1] / nav_series.nav[:-1]),
                0.0,
            )

    return pd.DataFrame(contributions, index=nav_series.dates[1:])
