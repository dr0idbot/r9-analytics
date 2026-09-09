"""Tests for missing data handling and data quality checks."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from shared.analytics.missing_data import (
    DataQuality,
    DataQualityReport,
    CalculationResult,
    check_data_quality,
    validate_returns,
    validate_prices,
    validate_matrix,
    require_minimum_data,
)


class TestCheckDataQuality:
    """Tests for check_data_quality."""

    def test_complete_data(self):
        data = pd.Series(range(100))
        report = check_data_quality(data, min_observations=30)
        assert report.quality == DataQuality.COMPLETE
        assert report.total_observations == 100
        assert report.valid_observations == 100
        assert report.missing_count == 0
        assert report.missing_pct == 0.0

    def test_insufficient_data(self):
        data = pd.Series(range(10))
        report = check_data_quality(data, min_observations=30)
        assert report.quality == DataQuality.INSUFFICIENT
        assert report.valid_observations == 10

    def test_missing_data(self):
        data = pd.Series([1, 2, np.nan, 4, np.nan] * 20)
        report = check_data_quality(data, min_observations=30)
        assert report.quality == DataQuality.SUFFICIENT
        assert report.missing_count > 0
        assert report.missing_pct > 0

    def test_empty_data(self):
        data = pd.Series(dtype=float)
        report = check_data_quality(data, min_observations=30)
        assert report.quality == DataQuality.MISSING

    def test_warnings(self):
        data = pd.Series([1, 2, np.nan, 4, np.nan] * 20)
        report = check_data_quality(data, min_observations=30)
        assert len(report.warnings) > 0


class TestValidateReturns:
    """Tests for validate_returns."""

    def test_normal_returns(self):
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.001, 0.02, 100))
        report = validate_returns(returns)
        assert report.quality == DataQuality.COMPLETE

    def test_extreme_returns(self):
        returns = pd.Series([0.01, -0.02, 0.6, -0.01, 0.02])
        report = validate_returns(returns, min_observations=3)
        assert any("extreme" in w.lower() for w in report.warnings)

    def test_constant_returns(self):
        returns = pd.Series([0.01] * 100)
        report = validate_returns(returns)
        assert any("zero variance" in w.lower() for w in report.warnings)


class TestValidatePrices:
    """Tests for validate_prices."""

    def test_normal_prices(self):
        prices = pd.Series([100, 105, 110, 108, 112])
        report = validate_prices(prices, min_observations=3)
        assert report.quality == DataQuality.COMPLETE

    def test_negative_prices(self):
        prices = pd.Series([100, 105, -10, 108, 112])
        report = validate_prices(prices, min_observations=3)
        assert any("negative" in w.lower() for w in report.warnings)

    def test_zero_prices(self):
        prices = pd.Series([100, 105, 0, 108, 112])
        report = validate_prices(prices, min_observations=3)
        assert any("zero" in w.lower() for w in report.warnings)


class TestValidateMatrix:
    """Tests for validate_matrix."""

    def test_normal_matrix(self):
        np.random.seed(42)
        matrix = pd.DataFrame({
            "A": np.random.normal(0.001, 0.02, 100),
            "B": np.random.normal(0.0005, 0.03, 100),
        })
        report = validate_matrix(matrix)
        assert report.quality == DataQuality.COMPLETE

    def test_perfect_correlation(self):
        matrix = pd.DataFrame({
            "A": [0.01, 0.02, 0.03, 0.04, 0.05],
            "B": [0.01, 0.02, 0.03, 0.04, 0.05],
        })
        report = validate_matrix(matrix, min_observations=3)
        assert any("correlated" in w.lower() for w in report.warnings)


class TestRequireMinimumData:
    """Tests for require_minimum_data."""

    def test_sufficient_data(self):
        data = pd.Series(range(100))
        require_minimum_data(data, min_observations=30)  # Should not raise

    def test_insufficient_data(self):
        data = pd.Series(range(10))
        with pytest.raises(ValueError, match="Insufficient data"):
            require_minimum_data(data, min_observations=30)

    def test_missing_data(self):
        data = pd.Series(dtype=float)
        with pytest.raises(ValueError, match="No data"):
            require_minimum_data(data, min_observations=30)
