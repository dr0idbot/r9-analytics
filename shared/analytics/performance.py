"""Performance and attribution calculations.

Beta, alpha, tracking error, information ratio, and risk-adjusted returns.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from shared.analytics.returns import price_returns, annualized_return, annualized_volatility

logger = logging.getLogger(__name__)


@dataclass
class RegressionResult:
    """Result of a linear regression.

    Attributes:
        beta: Sensitivity to benchmark.
        alpha: Intercept (Jensen's alpha).
        r_squared: Goodness of fit.
        t_stat: t-statistic for beta.
        p_value: p-value for beta.
        observations: Number of observations.
        residual_vol: Standard deviation of residuals.
    """

    beta: float | None
    alpha: float | None
    r_squared: float | None
    t_stat: float | None
    p_value: float | None
    observations: int
    residual_vol: float | None = None


@dataclass
class AttributionResult:
    """Result of a performance attribution.

    Attributes:
        tracking_error: Volatility of active returns.
        information_ratio: Alpha / tracking error.
        active_return: Portfolio return - benchmark return.
        beta: Portfolio beta.
        alpha: Jensen's alpha.
        observations: Number of observations.
    """

    tracking_error: float | None
    information_ratio: float | None
    active_return: float | None
    beta: float | None
    alpha: float | None
    observations: int


def linear_regression(
    asset_returns: pd.Series,
    benchmark_returns: pd.Series,
) -> RegressionResult:
    """Run OLS regression: asset = alpha + beta * benchmark + epsilon.

    Args:
        asset_returns: Asset return series.
        benchmark_returns: Benchmark return series.

    Returns:
        RegressionResult with beta, alpha, r_squared, etc.
    """
    # Align and clean
    aligned = pd.DataFrame({"asset": asset_returns, "benchmark": benchmark_returns}).dropna()
    if len(aligned) < 10:
        return RegressionResult(
            beta=None, alpha=None, r_squared=None, t_stat=None,
            p_value=None, observations=len(aligned),
        )

    x = aligned["benchmark"].values
    y = aligned["asset"].values

    slope, intercept, r_value, p_value, std_err = sp_stats.linregress(x, y)

    residual_vol = np.std(y - (intercept + slope * x), ddof=2)

    return RegressionResult(
        beta=float(slope),
        alpha=float(intercept),
        r_squared=float(r_value ** 2),
        t_stat=float(slope / std_err) if std_err > 0 else None,
        p_value=float(p_value),
        observations=len(aligned),
        residual_vol=float(residual_vol),
    )


def tracking_error(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    periods_per_year: int = 252,
    ddof: int = 1,
) -> float | None:
    """Compute tracking error (volatility of active returns).

    TE = std(portfolio - benchmark) * sqrt(periods_per_year)

    Args:
        portfolio_returns: Portfolio return series.
        benchmark_returns: Benchmark return series.
        periods_per_year: Annualization factor.
        ddof: Delta degrees of freedom.

    Returns:
        Annualized tracking error or None if insufficient data.
    """
    aligned = pd.DataFrame({
        "portfolio": portfolio_returns,
        "benchmark": benchmark_returns,
    }).dropna()

    if len(aligned) < 2:
        return None

    active = aligned["portfolio"] - aligned["benchmark"]
    return float(active.std(ddof=ddof) * np.sqrt(periods_per_year))


def information_ratio(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    periods_per_year: int = 252,
) -> float | None:
    """Compute information ratio.

    IR = mean(active return) / tracking error

    Args:
        portfolio_returns: Portfolio return series.
        benchmark_returns: Benchmark return series.
        periods_per_year: Annualization factor.

    Returns:
        Information ratio or None if insufficient data.
    """
    aligned = pd.DataFrame({
        "portfolio": portfolio_returns,
        "benchmark": benchmark_returns,
    }).dropna()

    if len(aligned) < 2:
        return None

    active = aligned["portfolio"] - aligned["benchmark"]
    te = active.std(ddof=1) * np.sqrt(periods_per_year)
    if te == 0:
        return None

    ann_active = active.mean() * periods_per_year
    return float(ann_active / te)


def sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.05,
    periods_per_year: int = 252,
) -> float | None:
    """Compute Sharpe ratio.

    SR = (R_p - R_f) / σ_p

    Args:
        returns: Portfolio return series.
        risk_free_rate: Annual risk-free rate.
        periods_per_year: Annualization factor.

    Returns:
        Sharpe ratio or None if insufficient data.
    """
    clean = returns.dropna()
    if len(clean) < 2:
        return None

    ann_ret = annualized_return(clean, periods_per_year)
    ann_vol = annualized_volatility(clean, periods_per_year)

    if ann_ret is None or ann_vol is None or ann_vol == 0:
        return None

    return float((ann_ret - risk_free_rate) / ann_vol)


def sortino_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.05,
    periods_per_year: int = 252,
) -> float | None:
    """Compute Sortino ratio.

    Uses downside deviation instead of total volatility.

    Args:
        returns: Portfolio return series.
        risk_free_rate: Annual risk-free rate.
        periods_per_year: Annualization factor.

    Returns:
        Sortino ratio or None if insufficient data.
    """
    clean = returns.dropna()
    if len(clean) < 2:
        return None

    downside = clean[clean < 0]
    if len(downside) < 2:
        return None

    ann_ret = annualized_return(clean, periods_per_year)
    if ann_ret is None:
        return None

    downside_dev = downside.std(ddof=1) * np.sqrt(periods_per_year)
    if downside_dev == 0:
        return None

    return float((ann_ret - risk_free_rate) / downside_dev)


def performance_attribution(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    risk_free_rate: float = 0.05,
    periods_per_year: int = 252,
) -> AttributionResult:
    """Compute full performance attribution.

    Args:
        portfolio_returns: Portfolio return series.
        benchmark_returns: Benchmark return series.
        risk_free_rate: Annual risk-free rate.
        periods_per_year: Annualization factor.

    Returns:
        AttributionResult with beta, alpha, TE, IR.
    """
    reg = linear_regression(portfolio_returns, benchmark_returns)
    te = tracking_error(portfolio_returns, benchmark_returns, periods_per_year)
    ir = information_ratio(portfolio_returns, benchmark_returns, periods_per_year)

    aligned = pd.DataFrame({
        "portfolio": portfolio_returns,
        "benchmark": benchmark_returns,
    }).dropna()

    if len(aligned) < 2:
        return AttributionResult(
            tracking_error=None, information_ratio=None,
            active_return=None, beta=None, alpha=None,
            observations=len(aligned),
        )

    ann_port = aligned["portfolio"].mean() * periods_per_year
    ann_bench = aligned["benchmark"].mean() * periods_per_year
    active_return = ann_port - ann_bench

    return AttributionResult(
        tracking_error=te,
        information_ratio=ir,
        active_return=float(active_return),
        beta=reg.beta,
        alpha=reg.alpha * periods_per_year if reg.alpha is not None else None,
        observations=reg.observations,
    )
