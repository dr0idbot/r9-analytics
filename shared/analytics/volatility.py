"""Volatility and diversification calculations.

Canonical implementations with proper ddof handling and edge cases.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from shared.analytics.returns import price_returns, log_returns, annualized_volatility

logger = logging.getLogger(__name__)


@dataclass
class VolatilityResult:
    """Result of a volatility calculation.

    Attributes:
        value: Annualized volatility.
        method: Calculation method used.
        observations: Number of observations used.
        annualization_factor: Periods per year used.
    """

    value: float | None
    method: str
    observations: int
    annualization_factor: int = 252


def realized_volatility(
    returns: pd.Series,
    periods_per_year: int = 252,
    ddof: int = 1,
) -> VolatilityResult:
    """Compute realized volatility from returns.

    This is the standard deviation of returns, annualized.

    Args:
        returns: Return series (simple or log).
        periods_per_year: Annualization factor (252 for daily).
        ddof: Delta degrees of freedom (1 for sample, 0 for population).

    Returns:
        VolatilityResult with annualized volatility.
    """
    if len(returns) < 2:
        return VolatilityResult(value=None, method="realized", observations=len(returns), annualization_factor=periods_per_year)

    clean = returns.dropna()
    if len(clean) < 2:
        return VolatilityResult(value=None, method="realized", observations=len(clean), annualization_factor=periods_per_year)

    daily_vol = clean.std(ddof=ddof)
    ann_vol = daily_vol * np.sqrt(periods_per_year)

    return VolatilityResult(value=float(ann_vol), method="realized", observations=len(clean), annualization_factor=periods_per_year)


def parkinson_volatility(
    high: pd.Series,
    low: pd.Series,
    periods_per_year: int = 252,
) -> VolatilityResult:
    """Compute Parkinson volatility from high/low prices.

    Uses the Parkinson (1980) range-based estimator:
    σ² = (1/4n ln(2)) Σ ln(H_i/L_i)²

    This is more efficient than close-to-close volatility.

    Args:
        high: High price series.
        low: Low price series.
        periods_per_year: Annualization factor.

    Returns:
        VolatilityResult with annualized volatility.
    """
    if len(high) < 1 or len(low) < 1:
        return VolatilityResult(value=None, method="parkinson", observations=0, annualization_factor=periods_per_year)

    # Align series
    aligned = pd.DataFrame({"high": high, "low": low}).dropna()
    if len(aligned) < 1:
        return VolatilityResult(value=None, method="parkinson", observations=0, annualization_factor=periods_per_year)

    log_hl = np.log(aligned["high"] / aligned["low"])
    variance = (log_hl ** 2).sum() / (4 * len(aligned) * np.log(2))
    daily_vol = np.sqrt(variance)
    ann_vol = daily_vol * np.sqrt(periods_per_year)

    return VolatilityResult(value=float(ann_vol), method="parkinson", observations=len(aligned), annualization_factor=periods_per_year)


def garman_klass_volatility(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    periods_per_year: int = 252,
) -> VolatilityResult:
    """Compute Garman-Klass volatility from OHLC data.

    Uses the Garman-Klass (1980) estimator:
    σ² = 0.5 ln(H/L)² - (2ln2-1) ln(C/O)²

    Args:
        open_: Open price series.
        high: High price series.
        low: Low price series.
        close: Close price series.
        periods_per_year: Annualization factor.

    Returns:
        VolatilityResult with annualized volatility.
    """
    aligned = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}).dropna()
    if len(aligned) < 1:
        return VolatilityResult(value=None, method="garman_klass", observations=0, annualization_factor=periods_per_year)

    log_hl = np.log(aligned["high"] / aligned["low"])
    log_co = np.log(aligned["close"] / aligned["open"])

    variance = 0.5 * (log_hl ** 2).sum() / len(aligned) - (2 * np.log(2) - 1) * (log_co ** 2).sum() / len(aligned)
    daily_vol = np.sqrt(max(variance, 0))
    ann_vol = daily_vol * np.sqrt(periods_per_year)

    return VolatilityResult(value=float(ann_vol), method="garman_klass", observations=len(aligned), annualization_factor=periods_per_year)


def semi_deviation(
    returns: pd.Series,
    periods_per_year: int = 252,
    ddof: int = 1,
) -> VolatilityResult:
    """Compute semi-deviation (downside volatility).

    Only considers returns below zero.

    Args:
        returns: Return series.
        periods_per_year: Annualization factor.
        ddof: Delta degrees of freedom.

    Returns:
        VolatilityResult with annualized semi-deviation.
    """
    if len(returns) < 2:
        return VolatilityResult(value=None, method="semi_deviation", observations=len(returns), annualization_factor=periods_per_year)

    clean = returns.dropna()
    downside = clean[clean < 0]
    if len(downside) < 2:
        return VolatilityResult(value=None, method="semi_deviation", observations=len(downside), annualization_factor=periods_per_year)

    daily_semi = downside.std(ddof=ddof)
    ann_semi = daily_semi * np.sqrt(periods_per_year)

    return VolatilityResult(value=float(ann_semi), method="semi_deviation", observations=len(downside), annualization_factor=periods_per_year)


def portfolio_volatility(
    returns_matrix: pd.DataFrame,
    weights: np.ndarray | pd.Series,
    periods_per_year: int = 252,
    ddof: int = 1,
) -> VolatilityResult:
    """Compute portfolio volatility from returns matrix and weights.

    σ_p = sqrt(w' Σ w) * sqrt(periods_per_year)

    Args:
        returns_matrix: DataFrame with assets as columns, returns as rows.
        weights: Portfolio weights array (must sum to 1).
        periods_per_year: Annualization factor.
        ddof: Delta degrees of freedom for covariance estimation.

    Returns:
        VolatilityResult with annualized portfolio volatility.
    """
    if returns_matrix.empty or len(weights) != len(returns_matrix.columns):
        return VolatilityResult(value=None, method="portfolio", observations=0, annualization_factor=periods_per_year)

    clean = returns_matrix.dropna()
    if len(clean) < 2:
        return VolatilityResult(value=None, method="portfolio", observations=len(clean), annualization_factor=periods_per_year)

    w = np.asarray(weights)
    cov = clean.cov(ddof=ddof).values
    var_p = w @ cov @ w
    daily_vol = np.sqrt(max(var_p, 0))
    ann_vol = daily_vol * np.sqrt(periods_per_year)

    return VolatilityResult(value=float(ann_vol), method="portfolio", observations=len(clean), annualization_factor=periods_per_year)


def diversification_ratio(
    returns_matrix: pd.DataFrame,
    weights: np.ndarray | pd.Series,
    periods_per_year: int = 252,
) -> float | None:
    """Compute diversification ratio.

    DR = Σ(w_i * σ_i) / σ_p

    DR > 1 indicates diversification benefit.

    Args:
        returns_matrix: DataFrame with assets as columns.
        weights: Portfolio weights.
        periods_per_year: Annualization factor.

    Returns:
        Diversification ratio or None if insufficient data.
    """
    if returns_matrix.empty or len(weights) != len(returns_matrix.columns):
        return None

    clean = returns_matrix.dropna()
    if len(clean) < 2:
        return None

    w = np.asarray(weights)

    # Individual volatilities
    individual_vols = clean.std(ddof=1) * np.sqrt(periods_per_year)
    weighted_avg_vol = np.sum(w * individual_vols.values)

    # Portfolio volatility
    port_vol_result = portfolio_volatility(returns_matrix, weights, periods_per_year)
    if port_vol_result.value is None or port_vol_result.value == 0:
        return None

    return float(weighted_avg_vol / port_vol_result.value)
