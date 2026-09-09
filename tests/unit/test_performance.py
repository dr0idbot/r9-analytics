"""Tests for performance and attribution calculations."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from shared.analytics.performance import (
    RegressionResult,
    AttributionResult,
    linear_regression,
    tracking_error,
    information_ratio,
    sharpe_ratio,
    sortino_ratio,
    performance_attribution,
)


class TestLinearRegression:
    """Tests for linear_regression."""

    def test_perfect_correlation(self):
        x = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        y = 2 * x + 1
        result = linear_regression(y, x)
        assert result.beta is not None
        assert abs(result.beta - 2.0) < 1e-10
        assert abs(result.alpha - 1.0) < 1e-10
        assert result.r_squared == pytest.approx(1.0)

    def test_no_correlation(self):
        np.random.seed(42)
        x = pd.Series(np.random.normal(0, 1, 1000))
        y = pd.Series(np.random.normal(0, 1, 1000))
        result = linear_regression(y, x)
        assert result.beta is not None
        assert abs(result.beta) < 0.1  # Should be close to 0
        assert result.r_squared < 0.05  # Should be close to 0

    def test_insufficient_data(self):
        x = pd.Series([1.0, 2.0, 3.0])
        y = pd.Series([2.0, 4.0, 6.0])
        result = linear_regression(y, x)
        assert result.beta is None

    def test_t_stat(self):
        np.random.seed(42)
        x = pd.Series(np.random.normal(0, 1, 100))
        y = 2 * x + np.random.normal(0, 0.1, 100)
        result = linear_regression(y, x)
        assert result.t_stat is not None
        assert result.t_stat > 10  # Should be highly significant

    def test_p_value(self):
        np.random.seed(42)
        x = pd.Series(np.random.normal(0, 1, 100))
        y = 2 * x + np.random.normal(0, 0.1, 100)
        result = linear_regression(y, x)
        assert result.p_value is not None
        assert result.p_value < 0.001


class TestTrackingError:
    """Tests for tracking_error."""

    def test_basic(self):
        np.random.seed(42)
        portfolio = pd.Series(np.random.normal(0.001, 0.02, 100))
        benchmark = pd.Series(np.random.normal(0.0005, 0.018, 100))
        result = tracking_error(portfolio, benchmark)
        assert result is not None
        assert result > 0

    def test_identical_returns(self):
        returns = pd.Series([0.01] * 100)
        result = tracking_error(returns, returns)
        assert result is not None
        assert result < 1e-10

    def test_insufficient_data(self):
        portfolio = pd.Series([0.01])
        benchmark = pd.Series([0.005])
        result = tracking_error(portfolio, benchmark)
        assert result is None


class TestInformationRatio:
    """Tests for information_ratio."""

    def test_basic(self):
        np.random.seed(42)
        portfolio = pd.Series(np.random.normal(0.001, 0.02, 100))
        benchmark = pd.Series(np.random.normal(0.0005, 0.018, 100))
        result = information_ratio(portfolio, benchmark)
        assert result is not None

    def test_identical_returns(self):
        returns = pd.Series([0.01] * 100)
        result = information_ratio(returns, returns)
        assert result is None  # Zero tracking error

    def test_insufficient_data(self):
        result = information_ratio(pd.Series([0.01]), pd.Series([0.005]))
        assert result is None


class TestSharpeRatio:
    """Tests for sharpe_ratio."""

    def test_basic(self):
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.001, 0.02, 1000))
        result = sharpe_ratio(returns)
        assert result is not None

    def test_high_return(self):
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.005, 0.02, 1000))
        result = sharpe_ratio(returns)
        assert result is not None
        assert result > 0

    def test_insufficient_data(self):
        result = sharpe_ratio(pd.Series([0.01]))
        assert result is None

    def test_constant_returns(self):
        returns = pd.Series([0.01] * 100)
        result = sharpe_ratio(returns)
        # Constant returns: very high Sharpe (approaches infinity)
        assert result is not None
        assert abs(result) > 1e10


class TestSortinoRatio:
    """Tests for sortino_ratio."""

    def test_basic(self):
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.001, 0.02, 1000))
        result = sortino_ratio(returns)
        assert result is not None

    def test_all_positive_returns(self):
        returns = pd.Series([0.01, 0.02, 0.015, 0.008])
        result = sortino_ratio(returns)
        assert result is None  # No downside

    def test_insufficient_data(self):
        result = sortino_ratio(pd.Series([0.01]))
        assert result is None


class TestPerformanceAttribution:
    """Tests for performance_attribution."""

    def test_basic(self):
        np.random.seed(42)
        portfolio = pd.Series(np.random.normal(0.001, 0.02, 100))
        benchmark = pd.Series(np.random.normal(0.0005, 0.018, 100))
        result = performance_attribution(portfolio, benchmark)
        assert result.beta is not None
        assert result.alpha is not None
        assert result.tracking_error is not None
        assert result.information_ratio is not None
        assert result.active_return is not None

    def test_insufficient_data(self):
        portfolio = pd.Series([0.01])
        benchmark = pd.Series([0.005])
        result = performance_attribution(portfolio, benchmark)
        assert result.beta is None

    def test_active_return_sign(self):
        """Outperforming portfolio should have positive active return."""
        np.random.seed(42)
        # Portfolio consistently outperforms
        benchmark = pd.Series(np.random.normal(0.0005, 0.018, 100))
        portfolio = benchmark + 0.001
        result = performance_attribution(portfolio, benchmark)
        assert result.active_return > 0
