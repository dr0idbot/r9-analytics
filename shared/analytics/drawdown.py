"""Drawdown and recovery analysis.

Maximum drawdown, drawdown duration, recovery time, and underwater series.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class DrawdownPeriod:
    """A single drawdown period.

    Attributes:
        start_date: Date when drawdown began (peak).
        end_date: Date of maximum drawdown (trough).
        recovery_date: Date of recovery (if recovered).
        drawdown: Maximum drawdown (negative value).
        duration_days: Number of days from start to trough.
        recovery_days: Number of days from trough to recovery.
        is_recovered: Whether the drawdown has been recovered.
    """

    start_date: date | str | None = None
    end_date: date | str | None = None
    recovery_date: date | str | None = None
    drawdown: float = 0.0
    duration_days: int = 0
    recovery_days: int | None = None
    is_recovered: bool = False


@dataclass
class DrawdownAnalysis:
    """Complete drawdown analysis.

    Attributes:
        max_drawdown: Maximum drawdown (negative value).
        max_drawdown_start: Start date of maximum drawdown.
        max_drawdown_end: End date of maximum drawdown.
        max_drawdown_recovery: Recovery date (if recovered).
        max_drawdown_duration: Duration of maximum drawdown.
        drawdown_series: Time series of drawdowns.
        periods: List of all significant drawdown periods.
        current_drawdown: Current drawdown (if in drawdown).
    """

    max_drawdown: float
    max_drawdown_start: date | str | None
    max_drawdown_end: date | str | None
    max_drawdown_recovery: date | str | None
    max_drawdown_duration: int
    drawdown_series: pd.Series
    periods: list[DrawdownPeriod]
    current_drawdown: float


def drawdown_series(prices: pd.Series) -> pd.Series:
    """Compute drawdown series from price series.

    DD_t = (P_t - P_peak) / P_peak

    Args:
        prices: Price or NAV series.

    Returns:
        Series of drawdowns (negative values).
    """
    if len(prices) < 1:
        return pd.Series(dtype=float)

    cumulative_max = prices.cummax()
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = (prices - cumulative_max) / cumulative_max
    return dd.fillna(0.0)


def max_drawdown(prices: pd.Series) -> float:
    """Compute maximum drawdown.

    Args:
        prices: Price or NAV series.

    Returns:
        Maximum drawdown as a negative number.
    """
    dd = drawdown_series(prices)
    if len(dd) == 0:
        return 0.0
    return float(dd.min())


def max_drawdown_with_dates(prices: pd.Series) -> DrawdownPeriod:
    """Compute maximum drawdown with start, end, and recovery dates.

    Args:
        prices: Price or NAV series with date index.

    Returns:
        DrawdownPeriod with full details.
    """
    if len(prices) < 2:
        return DrawdownPeriod(drawdown=0.0)

    dd = drawdown_series(prices)
    min_dd = dd.min()

    if min_dd == 0:
        return DrawdownPeriod(drawdown=0.0)

    # Find the trough
    trough_idx = dd.idxmin()
    trough_date = trough_idx

    # Find the peak before trough (start of drawdown)
    peak_before = prices.loc[:trough_date].idxmax()
    peak_date = peak_before

    # Find recovery (first time price exceeds peak AFTER trough)
    peak_value = prices.loc[peak_date]
    after_trough = prices.loc[trough_date:]

    recovery_date = None
    is_recovered = False
    recovery_days = None

    # Look for first price >= peak_value, excluding the trough itself
    for i, (d, p) in enumerate(after_trough.items()):
        if i == 0:
            continue  # Skip trough
        if p >= peak_value:
            recovery_date = d
            is_recovered = True
            if hasattr(trough_date, "days") and hasattr(recovery_date, "days"):
                recovery_days = (recovery_date - trough_date).days
            break

    # Calculate duration
    duration_days = 0
    if hasattr(peak_date, "days") and hasattr(trough_date, "days"):
        duration_days = (trough_date - peak_date).days

    return DrawdownPeriod(
        start_date=peak_date,
        end_date=trough_date,
        recovery_date=recovery_date,
        drawdown=float(min_dd),
        duration_days=duration_days,
        recovery_days=recovery_days,
        is_recovered=is_recovered,
    )


def drawdown_periods(prices: pd.Series, threshold: float = -0.05) -> list[DrawdownPeriod]:
    """Find all drawdown periods exceeding a threshold.

    Args:
        prices: Price or NAV series.
        threshold: Minimum drawdown to include (negative, e.g. -0.05 for 5%).

    Returns:
        List of DrawdownPeriod objects.
    """
    if len(prices) < 2:
        return []

    dd = drawdown_series(prices)
    periods = []

    in_drawdown = False
    peak_date = None
    peak_value = None

    for i, (current_date, current_dd) in enumerate(dd.items()):
        if not in_drawdown and current_dd < threshold:
            # Start of new drawdown
            in_drawdown = True
            peak_date = prices.loc[:current_date].idxmax()
            peak_value = prices.loc[peak_date]
        elif in_drawdown and current_dd >= 0:
            # Recovery
            in_drawdown = False
            trough_date = dd.loc[peak_date:current_date].idxmin()
            trough_dd = dd.loc[trough_date]

            recovery_days = None
            if hasattr(trough_date, "days") and hasattr(current_date, "days"):
                recovery_days = (current_date - trough_date).days

            duration_days = 0
            if hasattr(peak_date, "days") and hasattr(trough_date, "days"):
                duration_days = (trough_date - peak_date).days

            periods.append(DrawdownPeriod(
                start_date=peak_date,
                end_date=trough_date,
                recovery_date=current_date,
                drawdown=float(trough_dd),
                duration_days=duration_days,
                recovery_days=recovery_days,
                is_recovered=True,
            ))

    # Handle ongoing drawdown
    if in_drawdown:
        trough_date = dd.loc[peak_date:].idxmin()
        trough_dd = dd.loc[trough_date]

        duration_days = 0
        if hasattr(peak_date, "days") and hasattr(trough_date, "days"):
            duration_days = (trough_date - peak_date).days

        periods.append(DrawdownPeriod(
            start_date=peak_date,
            end_date=trough_date,
            drawdown=float(trough_dd),
            duration_days=duration_days,
            is_recovered=False,
        ))

    return sorted(periods, key=lambda p: p.drawdown)


def current_drawdown(prices: pd.Series) -> float:
    """Compute current drawdown from latest price.

    Args:
        prices: Price or NAV series.

    Returns:
        Current drawdown (negative value).
    """
    if len(prices) < 1:
        return 0.0

    dd = drawdown_series(prices)
    return float(dd.iloc[-1])


def drawdown_duration(prices: pd.Series) -> int:
    """Compute current drawdown duration in days.

    Args:
        prices: Price or NAV series.

    Returns:
        Number of days since last peak.
    """
    if len(prices) < 2:
        return 0

    peak = prices.cummax()
    at_peak = prices >= peak

    if at_peak.iloc[-1]:
        return 0

    # Find last time we were at a peak
    peak_dates = at_peak[at_peak].index
    if len(peak_dates) == 0:
        return 0

    last_peak_idx = peak_dates[-1]
    current_date = prices.index[-1]

    # Check if these are date-like objects (have subtraction defined)
    try:
        delta = current_date - last_peak_idx
        return delta.days
    except (TypeError, AttributeError):
        return 0
