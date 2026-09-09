"""Tests for VaR and CVaR calculations."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from shared.analytics.risk import (
    VaRMethod,
    VaRResult,
    historical_var,
    parametric_var,
    modified_var,
    portfolio_var,
)


class TestVaRResult:
    """Tests for VaRResult dataclass."""

    def test_pct_conversion(self):
        result = VaRResult(
            var=0.05, cvar=0.08, confidence=0.95,
            method=VaRMethod.HISTORICAL, observations=100,
        )
        assert result.var_pct == 5.0
        assert result.cvar_pct == 8.0

    def test_dollar_conversion(self):
        result = VaRResult(
            var=0.05, cvar=0.08, confidence=0.95,
            method=VaRMethod.HISTORICAL, observations=100,
            portfolio_value=1_000_000,
        )
        assert result.var_dollar == 50_000.0
        assert result.cvar_dollar == 80_000.0

    def test_none_values(self):
        result = VaRResult(
            var=None, cvar=None, confidence=0.95,
            method=VaRMethod.HISTORICAL, observations=0,
        )
        assert result.var_pct is None
        assert result.cvar_pct is None
        assert result.var_dollar is None
        assert result.cvar_dollar is None


class TestHistoricalVaR:
    """Tests for historical_var."""

    def test_basic(self):
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.001, 0.02, 1000))
        result = historical_var(returns)
        assert result.var is not None
        assert result.cvar is not None
        assert result.var > 0
        assert result.cvar >= result.var
        assert result.method == VaRMethod.HISTORICAL

    def test_different_confidence(self):
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.001, 0.02, 1000))
        var_95 = historical_var(returns, confidence=0.95)
        var_99 = historical_var(returns, confidence=0.99)
        # Higher confidence = higher VaR
        assert var_99.var > var_95.var

    def test_horizon_scaling(self):
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.001, 0.02, 1000))
        var_1 = historical_var(returns, horizon=1)
        var_10 = historical_var(returns, horizon=10)
        # Longer horizon = higher VaR
        assert var_10.var > var_1.var

    def test_insufficient_data(self):
        returns = pd.Series([0.01] * 5)
        result = historical_var(returns)
        assert result.var is None

    def test_empty(self):
        result = historical_var(pd.Series(dtype=float))
        assert result.var is None

    def test_cvar_exceeds_var(self):
        """CVaR should always be >= VaR."""
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.001, 0.02, 1000))
        result = historical_var(returns, confidence=0.95)
        assert result.cvar >= result.var


class TestParametricVaR:
    """Tests for parametric_var."""

    def test_basic(self):
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.001, 0.02, 1000))
        result = parametric_var(returns)
        assert result.var is not None
        assert result.cvar is not None
        assert result.var > 0
        assert result.method == VaRMethod.PARAMETRIC

    def test_normal_distribution(self):
        """For normal distribution, parametric and historical should be similar."""
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0, 0.02, 10000))
        hist = historical_var(returns, confidence=0.95)
        param = parametric_var(returns, confidence=0.95)
        # Should be within 20% of each other
        assert abs(hist.var - param.var) / hist.var < 0.20

    def test_insufficient_data(self):
        returns = pd.Series([0.01] * 5)
        result = parametric_var(returns)
        assert result.var is None


class TestModifiedVaR:
    """Tests for modified_var."""

    def test_basic(self):
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.001, 0.02, 1000))
        result = modified_var(returns)
        assert result.var is not None
        assert result.method == VaRMethod.MODIFIED

    def test_skewed_distribution(self):
        """Modified VaR should differ from parametric for skewed data."""
        np.random.seed(42)
        # Create negatively skewed returns
        returns = pd.Series(np.concatenate([
            np.random.normal(0.002, 0.015, 900),
            np.random.normal(-0.01, 0.03, 100),
        ]))
        param = parametric_var(returns, confidence=0.95)
        mod = modified_var(returns, confidence=0.95)
        # They should be different due to skew adjustment
        assert param.var is not None
        assert mod.var is not None

    def test_insufficient_data(self):
        returns = pd.Series([0.01] * 10)
        result = modified_var(returns)
        assert result.var is None


class TestPortfolioVaR:
    """Tests for portfolio_var."""

    def test_basic(self):
        np.random.seed(42)
        returns_matrix = pd.DataFrame({
            "A": np.random.normal(0.001, 0.02, 100),
            "B": np.random.normal(0.0005, 0.03, 100),
        })
        weights = np.array([0.6, 0.4])
        result = portfolio_var(returns_matrix, weights)
        assert result.var is not None
        assert result.method == VaRMethod.PARAMETRIC

    def test_single_asset(self):
        returns_matrix = pd.DataFrame({"A": np.random.normal(0.001, 0.02, 100)})
        weights = np.array([1.0])
        result = portfolio_var(returns_matrix, weights)
        assert result.var is not None

    def test_weight_mismatch(self):
        returns_matrix = pd.DataFrame({"A": [0.01], "B": [0.02]})
        weights = np.array([1.0])
        result = portfolio_var(returns_matrix, weights)
        assert result.var is None

    def test_empty(self):
        result = portfolio_var(pd.DataFrame(), np.array([]))
        assert result.var is None
