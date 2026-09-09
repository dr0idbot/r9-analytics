"""Tests for canonical return engine."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from shared.analytics.returns import (
    annualized_return,
    annualized_volatility,
    cumulative_return,
    log_returns,
    price_returns,
    total_returns,
)


class TestPriceReturns:
    """Tests for price_returns function."""

    def test_basic(self):
        prices = pd.Series([100, 110, 105, 115])
        returns = price_returns(prices)
        expected = [np.nan, 0.10, -5 / 110, 10 / 105]
        assert len(returns) == 4
        assert returns.iloc[0] != returns.iloc[0]  # NaN check
        assert abs(returns.iloc[1] - 0.10) < 1e-10
        assert abs(returns.iloc[2] - (-5 / 110)) < 1e-10
        assert abs(returns.iloc[3] - (10 / 105)) < 1e-10

    def test_empty(self):
        prices = pd.Series([], dtype=float)
        returns = price_returns(prices)
        assert len(returns) == 0

    def test_single_value(self):
        prices = pd.Series([100])
        returns = price_returns(prices)
        assert len(returns) == 0

    def test_constant_prices(self):
        prices = pd.Series([100, 100, 100, 100])
        returns = price_returns(prices)
        assert returns.iloc[1:] .abs().max() < 1e-10


class TestTotalReturns:
    """Tests for total_returns function."""

    def test_basic(self):
        adjusted = pd.Series([100, 110, 105, 115])
        returns = total_returns(adjusted)
        assert len(returns) == 4
        assert returns.iloc[0] != returns.iloc[0]  # NaN
        assert abs(returns.iloc[1] - 0.10) < 1e-10

    def test_with_dividends(self):
        # Adjusted prices account for dividends
        adjusted = pd.Series([100, 108, 103, 112])
        returns = total_returns(adjusted)
        assert len(returns) == 4


class TestLogReturns:
    """Tests for log_returns function."""

    def test_basic(self):
        prices = pd.Series([100, 110, 105, 115])
        returns = log_returns(prices)
        assert len(returns) == 4
        assert returns.iloc[0] != returns.iloc[0]  # NaN
        # log(110/100) = log(1.1)
        assert abs(returns.iloc[1] - np.log(1.1)) < 1e-10

    def test_symmetry(self):
        # log(110/100) = -log(100/110)
        prices = pd.Series([100, 110])
        returns = log_returns(prices)
        # returns.iloc[1] = log(110/100)
        # log(100/110) = -log(110/100)
        assert abs(returns.iloc[1] - np.log(110 / 100)) < 1e-10
        assert abs(-returns.iloc[1] - np.log(100 / 110)) < 1e-10


class TestCumulativeReturn:
    """Tests for cumulative_return function."""

    def test_basic(self):
        returns = pd.Series([0.10, -0.05, 0.08])
        cum = cumulative_return(returns)
        expected = [(1.10) - 1, (1.10 * 0.95) - 1, (1.10 * 0.95 * 1.08) - 1]
        assert len(cum) == 3
        for i, e in enumerate(expected):
            assert abs(cum.iloc[i] - e) < 1e-10

    def test_empty(self):
        returns = pd.Series([], dtype=float)
        cum = cumulative_return(returns)
        assert len(cum) == 0


class TestAnnualizedReturn:
    """Tests for annualized_return function."""

    def test_basic(self):
        # 0.1% daily for 252 days
        returns = pd.Series([0.001] * 252)
        ann = annualized_return(returns, periods_per_year=252)
        expected = (1.001) ** 252 - 1
        assert ann is not None
        assert abs(ann - expected) < 1e-10

    def test_insufficient_data(self):
        returns = pd.Series([0.01])
        ann = annualized_return(returns, periods_per_year=252)
        assert ann is None

    def test_two_observations(self):
        # Two observations is mathematically valid
        returns = pd.Series([0.01, 0.02])
        ann = annualized_return(returns, periods_per_year=252)
        assert ann is not None

    def test_constant_return(self):
        returns = pd.Series([0.0] * 100)
        ann = annualized_return(returns, periods_per_year=252)
        assert ann is not None
        assert abs(ann) < 1e-10


class TestAnnualizedVolatility:
    """Tests for annualized_volatility function."""

    def test_constant_returns(self):
        # Constant returns should have zero volatility
        returns = pd.Series([0.01] * 100)
        vol = annualized_volatility(returns, periods_per_year=252, ddof=1)
        assert vol is not None
        assert abs(vol) < 1e-10

    def test_basic(self):
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.001, 0.02, 252))
        vol = annualized_volatility(returns, periods_per_year=252, ddof=1)
        assert vol is not None
        assert vol > 0
        # Should be close to 0.02 * sqrt(252) ≈ 0.317
        assert 0.2 < vol < 0.5

    def test_insufficient_data(self):
        returns = pd.Series([0.01])
        vol = annualized_volatility(returns, periods_per_year=252)
        assert vol is None
