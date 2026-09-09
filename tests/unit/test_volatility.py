"""Tests for volatility and diversification calculations."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from shared.analytics.volatility import (
    VolatilityResult,
    realized_volatility,
    parkinson_volatility,
    garman_klass_volatility,
    semi_deviation,
    portfolio_volatility,
    diversification_ratio,
)


class TestRealizedVolatility:
    """Tests for realized_volatility."""

    def test_basic(self):
        returns = pd.Series([0.01, -0.02, 0.015, -0.005, 0.008])
        result = realized_volatility(returns)
        assert result.value is not None
        assert result.value > 0
        assert result.method == "realized"
        assert result.observations == 5

    def test_empty(self):
        result = realized_volatility(pd.Series(dtype=float))
        assert result.value is None

    def test_single_value(self):
        result = realized_volatility(pd.Series([0.01]))
        assert result.value is None

    def test_constant_returns(self):
        returns = pd.Series([0.01] * 10)
        result = realized_volatility(returns)
        assert result.value is not None
        assert result.value < 1e-10

    def test_different_ddof(self):
        returns = pd.Series([0.01, -0.02, 0.015, -0.005])
        result_1 = realized_volatility(returns, ddof=1)
        result_0 = realized_volatility(returns, ddof=0)
        # Sample std > population std
        assert result_1.value > result_0.value

    def test_annualization(self):
        returns = pd.Series([0.01, -0.02, 0.015, -0.005, 0.008])
        result_252 = realized_volatility(returns, periods_per_year=252)
        result_52 = realized_volatility(returns, periods_per_year=52)
        # More periods = higher annualized vol
        assert result_252.value > result_52.value


class TestParkinsonVolatility:
    """Tests for parkinson_volatility."""

    def test_basic(self):
        high = pd.Series([100, 110, 105, 115])
        low = pd.Series([95, 100, 98, 108])
        result = parkinson_volatility(high, low)
        assert result.value is not None
        assert result.value > 0
        assert result.method == "parkinson"

    def test_empty(self):
        result = parkinson_volatility(pd.Series(dtype=float), pd.Series(dtype=float))
        assert result.value is None

    def test_high_equals_low(self):
        high = pd.Series([100, 100, 100])
        low = pd.Series([100, 100, 100])
        result = parkinson_volatility(high, low)
        assert result.value == 0.0


class TestGarmanKlassVolatility:
    """Tests for garman_klass_volatility."""

    def test_basic(self):
        open_ = pd.Series([100, 105, 110])
        high = pd.Series([110, 115, 120])
        low = pd.Series([95, 100, 105])
        close = pd.Series([105, 110, 115])
        result = garman_klass_volatility(open_, high, low, close)
        assert result.value is not None
        assert result.value > 0
        assert result.method == "garman_klass"

    def test_empty(self):
        result = garman_klass_volatility(
            pd.Series(dtype=float), pd.Series(dtype=float),
            pd.Series(dtype=float), pd.Series(dtype=float),
        )
        assert result.value is None


class TestSemiDeviation:
    """Tests for semi_deviation."""

    def test_basic(self):
        returns = pd.Series([0.01, -0.02, 0.015, -0.005, -0.01])
        result = semi_deviation(returns)
        assert result.value is not None
        assert result.value > 0
        assert result.method == "semi_deviation"

    def test_all_positive(self):
        returns = pd.Series([0.01, 0.02, 0.015])
        result = semi_deviation(returns)
        assert result.value is None

    def test_empty(self):
        result = semi_deviation(pd.Series(dtype=float))
        assert result.value is None


class TestPortfolioVolatility:
    """Tests for portfolio_volatility."""

    def test_basic(self):
        np.random.seed(42)
        returns_matrix = pd.DataFrame({
            "A": np.random.normal(0.001, 0.02, 100),
            "B": np.random.normal(0.0005, 0.03, 100),
        })
        weights = np.array([0.6, 0.4])
        result = portfolio_volatility(returns_matrix, weights)
        assert result.value is not None
        assert result.value > 0
        assert result.method == "portfolio"

    def test_single_asset(self):
        returns_matrix = pd.DataFrame({"A": [0.01, -0.02, 0.015]})
        weights = np.array([1.0])
        result = portfolio_volatility(returns_matrix, weights)
        assert result.value is not None

    def test_weight_mismatch(self):
        returns_matrix = pd.DataFrame({"A": [0.01], "B": [0.02]})
        weights = np.array([1.0])  # Wrong length
        result = portfolio_volatility(returns_matrix, weights)
        assert result.value is None

    def test_correlation_reduces_vol(self):
        """Perfectly correlated assets have no diversification benefit."""
        returns_matrix = pd.DataFrame({
            "A": [0.01, -0.02, 0.015, -0.005],
            "B": [0.01, -0.02, 0.015, -0.005],
        })
        weights = np.array([0.5, 0.5])
        result = portfolio_volatility(returns_matrix, weights)
        # Should equal individual vol (no diversification)
        individual = realized_volatility(returns_matrix["A"])
        assert abs(result.value - individual.value) < 1e-10


class TestDiversificationRatio:
    """Tests for diversification_ratio."""

    def test_basic(self):
        np.random.seed(42)
        returns_matrix = pd.DataFrame({
            "A": np.random.normal(0.001, 0.02, 100),
            "B": np.random.normal(0.0005, 0.03, 100),
        })
        weights = np.array([0.6, 0.4])
        result = diversification_ratio(returns_matrix, weights)
        assert result is not None
        # DR should be > 1 for uncorrelated assets
        assert result > 1.0

    def test_perfect_correlation(self):
        """Perfectly correlated assets have DR = 1."""
        returns_matrix = pd.DataFrame({
            "A": [0.01, -0.02, 0.015, -0.005],
            "B": [0.01, -0.02, 0.015, -0.005],
        })
        weights = np.array([0.5, 0.5])
        result = diversification_ratio(returns_matrix, weights)
        assert result is not None
        assert abs(result - 1.0) < 1e-10

    def test_empty(self):
        result = diversification_ratio(pd.Series(dtype=float), np.array([]))
        assert result is None
