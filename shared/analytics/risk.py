"""Value at Risk (VaR) and Conditional VaR (CVaR) calculations.

Canonical implementations with multiple methodologies.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

logger = logging.getLogger(__name__)


class VaRMethod(Enum):
    """VaR calculation method."""

    HISTORICAL = "historical"
    PARAMETRIC = "parametric"
    MODIFIED = "modified"  # Cornish-Fisher


@dataclass
class VaRResult:
    """Result of a VaR or CVaR calculation.

    Attributes:
        var: Value at Risk (positive = loss).
        cvar: Conditional VaR / Expected Shortfall.
        confidence: Confidence level (e.g. 0.95).
        method: Calculation method.
        observations: Number of observations used.
        horizon: Holding period in days.
        portfolio_value: Optional portfolio value for dollar VaR.
    """

    var: float | None
    cvar: float | None
    confidence: float
    method: VaRMethod
    observations: int
    horizon: int = 1
    portfolio_value: float | None = None

    @property
    def var_pct(self) -> float | None:
        """VaR as percentage."""
        if self.var is None:
            return None
        return abs(self.var) * 100

    @property
    def cvar_pct(self) -> float | None:
        """CVaR as percentage."""
        if self.cvar is None:
            return None
        return abs(self.cvar) * 100

    @property
    def var_dollar(self) -> float | None:
        """VaR in dollar terms."""
        if self.var is None or self.portfolio_value is None:
            return None
        return abs(self.var) * self.portfolio_value

    @property
    def cvar_dollar(self) -> float | None:
        """CVaR in dollar terms."""
        if self.cvar is None or self.portfolio_value is None:
            return None
        return abs(self.cvar) * self.portfolio_value


def historical_var(
    returns: pd.Series,
    confidence: float = 0.95,
    horizon: int = 1,
    portfolio_value: float | None = None,
) -> VaRResult:
    """Compute Historical VaR using percentile method.

    VaR = -percentile(returns, 1-confidence)

    Args:
        returns: Return series.
        confidence: Confidence level (e.g. 0.95 for 95%).
        horizon: Holding period in days.
        portfolio_value: Optional portfolio value for dollar VaR.

    Returns:
        VaRResult with VaR and CVaR.
    """
    if len(returns) < 10:
        return VaRResult(
            var=None, cvar=None, confidence=confidence,
            method=VaRMethod.HISTORICAL, observations=len(returns), horizon=horizon,
            portfolio_value=portfolio_value,
        )

    clean = returns.dropna()
    if len(clean) < 10:
        return VaRResult(
            var=None, cvar=None, confidence=confidence,
            method=VaRMethod.HISTORICAL, observations=len(clean), horizon=horizon,
            portfolio_value=portfolio_value,
        )

    # Scale for horizon
    if horizon > 1:
        scaled = clean * np.sqrt(horizon)
    else:
        scaled = clean

    alpha = 1 - confidence
    var_value = -np.percentile(scaled, alpha * 100)

    # CVaR is the mean of returns below VaR
    tail = scaled[scaled <= -var_value]
    cvar_value = -tail.mean() if len(tail) > 0 else var_value

    return VaRResult(
        var=float(var_value),
        cvar=float(cvar_value),
        confidence=confidence,
        method=VaRMethod.HISTORICAL,
        observations=len(clean),
        horizon=horizon,
        portfolio_value=portfolio_value,
    )


def parametric_var(
    returns: pd.Series,
    confidence: float = 0.95,
    horizon: int = 1,
    portfolio_value: float | None = None,
) -> VaRResult:
    """Compute Parametric VaR (variance-covariance method).

    Assumes normal distribution:
    VaR = -(μ + z_α * σ)

    Args:
        returns: Return series.
        confidence: Confidence level.
        horizon: Holding period in days.
        portfolio_value: Optional portfolio value for dollar VaR.

    Returns:
        VaRResult with VaR and CVaR.
    """
    if len(returns) < 10:
        return VaRResult(
            var=None, cvar=None, confidence=confidence,
            method=VaRMethod.PARAMETRIC, observations=len(returns), horizon=horizon,
            portfolio_value=portfolio_value,
        )

    clean = returns.dropna()
    if len(clean) < 10:
        return VaRResult(
            var=None, cvar=None, confidence=confidence,
            method=VaRMethod.PARAMETRIC, observations=len(clean), horizon=horizon,
            portfolio_value=portfolio_value,
        )

    mu = clean.mean()
    sigma = clean.std(ddof=1)

    # Scale for horizon
    mu_h = mu * horizon
    sigma_h = sigma * np.sqrt(horizon)

    z = sp_stats.norm.ppf(1 - confidence)
    var_value = -(mu_h + z * sigma_h)

    # CVaR under normality
    pdf_z = sp_stats.norm.pdf(z)
    cvar_value = -(mu_h - sigma_h * pdf_z / (1 - confidence))

    return VaRResult(
        var=float(var_value),
        cvar=float(cvar_value),
        confidence=confidence,
        method=VaRMethod.PARAMETRIC,
        observations=len(clean),
        horizon=horizon,
        portfolio_value=portfolio_value,
    )


def modified_var(
    returns: pd.Series,
    confidence: float = 0.95,
    horizon: int = 1,
    portfolio_value: float | None = None,
) -> VaRResult:
    """Compute Modified VaR using Cornish-Fisher expansion.

    Adjusts parametric VaR for skewness and kurtosis.

    Args:
        returns: Return series.
        confidence: Confidence level.
        horizon: Holding period in days.
        portfolio_value: Optional portfolio value for dollar VaR.

    Returns:
        VaRResult with VaR and CVaR.
    """
    if len(returns) < 20:
        return VaRResult(
            var=None, cvar=None, confidence=confidence,
            method=VaRMethod.MODIFIED, observations=len(returns), horizon=horizon,
            portfolio_value=portfolio_value,
        )

    clean = returns.dropna()
    if len(clean) < 20:
        return VaRResult(
            var=None, cvar=None, confidence=confidence,
            method=VaRMethod.MODIFIED, observations=len(clean), horizon=horizon,
            portfolio_value=portfolio_value,
        )

    mu = clean.mean()
    sigma = clean.std(ddof=1)
    skew = clean.skew()
    kurt = clean.kurtosis()  # Excess kurtosis

    # Cornish-Fisher expansion
    z = sp_stats.norm.ppf(1 - confidence)
    z_cf = (
        z
        + (z**2 - 1) * skew / 6
        + (z**3 - 3*z) * kurt / 24
        - (2*z**3 - 5*z) * skew**2 / 36
    )

    # Scale for horizon
    mu_h = mu * horizon
    sigma_h = sigma * np.sqrt(horizon)

    var_value = -(mu_h + z_cf * sigma_h)

    # CVaR approximation using modified z
    pdf_z = sp_stats.norm.pdf(z_cf)
    cvar_value = -(mu_h - sigma_h * pdf_z / (1 - confidence))

    return VaRResult(
        var=float(var_value),
        cvar=float(cvar_value),
        confidence=confidence,
        method=VaRMethod.MODIFIED,
        observations=len(clean),
        horizon=horizon,
        portfolio_value=portfolio_value,
    )


def portfolio_var(
    returns_matrix: pd.DataFrame,
    weights: np.ndarray | pd.Series,
    confidence: float = 0.95,
    horizon: int = 1,
    portfolio_value: float | None = None,
) -> VaRResult:
    """Compute portfolio VaR from returns matrix and weights.

    Uses the parametric method with portfolio return distribution.

    Args:
        returns_matrix: DataFrame with assets as columns.
        weights: Portfolio weights.
        confidence: Confidence level.
        horizon: Holding period in days.
        portfolio_value: Optional portfolio value for dollar VaR.

    Returns:
        VaRResult with portfolio VaR and CVaR.
    """
    if returns_matrix.empty or len(weights) != len(returns_matrix.columns):
        return VaRResult(
            var=None, cvar=None, confidence=confidence,
            method=VaRMethod.PARAMETRIC, observations=0, horizon=horizon,
            portfolio_value=portfolio_value,
        )

    clean = returns_matrix.dropna()
    if len(clean) < 10:
        return VaRResult(
            var=None, cvar=None, confidence=confidence,
            method=VaRMethod.PARAMETRIC, observations=len(clean), horizon=horizon,
            portfolio_value=portfolio_value,
        )

    w = np.asarray(weights)
    portfolio_returns = clean.values @ w
    portfolio_series = pd.Series(portfolio_returns)

    return parametric_var(portfolio_series, confidence, horizon, portfolio_value)
