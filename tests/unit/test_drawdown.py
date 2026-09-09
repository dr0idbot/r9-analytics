"""Tests for drawdown and recovery analysis."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from shared.analytics.drawdown import (
    DrawdownPeriod,
    DrawdownAnalysis,
    drawdown_series,
    max_drawdown,
    max_drawdown_with_dates,
    drawdown_periods,
    current_drawdown,
    drawdown_duration,
)


def _make_prices(dates: list[date], values: list[float]) -> pd.Series:
    """Helper to create a price series."""
    return pd.Series(values, index=dates, dtype=float)


class TestDrawdownSeries:
    """Tests for drawdown_series."""

    def test_basic(self):
        dates = [date(2024, 1, i) for i in range(1, 6)]
        prices = _make_prices(dates, [100, 110, 105, 95, 108])
        dd = drawdown_series(prices)
        # Peak = 110 on Jan 2
        # DD: 0, 0, -5/110, -15/110, -2/110
        assert dd.iloc[0] == 0.0
        assert dd.iloc[1] == 0.0
        assert abs(dd.iloc[2] - (-5/110)) < 1e-10
        assert abs(dd.iloc[3] - (-15/110)) < 1e-10
        assert abs(dd.iloc[4] - (-2/110)) < 1e-10

    def test_empty(self):
        dd = drawdown_series(pd.Series(dtype=float))
        assert len(dd) == 0

    def test_monotonic_increase(self):
        dates = [date(2024, 1, i) for i in range(1, 6)]
        prices = _make_prices(dates, [100, 110, 120, 130, 140])
        dd = drawdown_series(prices)
        assert (dd == 0).all()


class TestMaxDrawdown:
    """Tests for max_drawdown."""

    def test_basic(self):
        dates = [date(2024, 1, i) for i in range(1, 6)]
        prices = _make_prices(dates, [100, 110, 105, 95, 108])
        result = max_drawdown(prices)
        assert result < 0
        assert abs(result - (-15/110)) < 1e-10

    def test_empty(self):
        result = max_drawdown(pd.Series(dtype=float))
        assert result == 0.0

    def test_no_drawdown(self):
        dates = [date(2024, 1, i) for i in range(1, 6)]
        prices = _make_prices(dates, [100, 110, 120, 130, 140])
        result = max_drawdown(prices)
        assert result == 0.0


class TestMaxDrawdownWithDates:
    """Tests for max_drawdown_with_dates."""

    def test_basic(self):
        dates = [date(2024, 1, i) for i in range(1, 8)]
        # Peak at 110, then drop to 90, recover to 112
        prices = _make_prices(dates, [100, 110, 105, 95, 90, 100, 112])
        result = max_drawdown_with_dates(prices)
        assert result.drawdown < 0
        assert result.start_date == date(2024, 1, 2)  # Peak
        assert result.end_date == date(2024, 1, 5)  # Trough
        assert result.is_recovered

    def test_no_drawdown(self):
        dates = [date(2024, 1, i) for i in range(1, 6)]
        prices = _make_prices(dates, [100, 110, 120, 130, 140])
        result = max_drawdown_with_dates(prices)
        assert result.drawdown == 0.0

    def test_ongoing_drawdown(self):
        dates = [date(2024, 1, i) for i in range(1, 6)]
        prices = _make_prices(dates, [100, 110, 100, 95, 92])
        result = max_drawdown_with_dates(prices)
        assert result.drawdown < 0
        assert not result.is_recovered

    def test_empty(self):
        result = max_drawdown_with_dates(pd.Series(dtype=float))
        assert result.drawdown == 0.0


class TestDrawdownPeriods:
    """Tests for drawdown_periods."""

    def test_basic(self):
        dates = [date(2024, 1, i) for i in range(1, 15)]
        # Two drawdowns: -10% and -8%
        prices = _make_prices(dates, [
            100, 110, 100, 95, 105, 115,  # First drawdown
            110, 100, 95, 105, 115, 120,  # Second drawdown
            118, 125,
        ])
        result = drawdown_periods(prices, threshold=-0.05)
        assert len(result) >= 2
        # Sorted by drawdown (most negative first)
        assert result[0].drawdown <= result[1].drawdown

    def test_threshold(self):
        dates = [date(2024, 1, i) for i in range(1, 8)]
        prices = _make_prices(dates, [100, 110, 105, 95, 100, 108, 115])
        # -5/110 = -4.5% (below -5% threshold)
        result_5 = drawdown_periods(prices, threshold=-0.05)
        # -5/110 = -4.5% (above -3% threshold)
        result_3 = drawdown_periods(prices, threshold=-0.03)
        assert len(result_3) >= len(result_5)

    def test_empty(self):
        result = drawdown_periods(pd.Series(dtype=float))
        assert len(result) == 0


class TestCurrentDrawdown:
    """Tests for current_drawdown."""

    def test_in_drawdown(self):
        dates = [date(2024, 1, i) for i in range(1, 6)]
        prices = _make_prices(dates, [100, 110, 105, 95, 92])
        result = current_drawdown(prices)
        assert result < 0

    def test_at_peak(self):
        dates = [date(2024, 1, i) for i in range(1, 6)]
        prices = _make_prices(dates, [100, 110, 105, 95, 115])
        result = current_drawdown(prices)
        assert result == 0.0

    def test_empty(self):
        result = current_drawdown(pd.Series(dtype=float))
        assert result == 0.0


class TestDrawdownDuration:
    """Tests for drawdown_duration."""

    def test_in_drawdown(self):
        dates = [date(2024, 1, i) for i in range(1, 8)]
        prices = _make_prices(dates, [100, 110, 105, 100, 95, 92, 88])
        result = drawdown_duration(prices)
        assert result == 5  # 5 days since peak on Jan 2

    def test_at_peak(self):
        dates = [date(2024, 1, i) for i in range(1, 6)]
        prices = _make_prices(dates, [100, 110, 105, 95, 115])
        result = drawdown_duration(prices)
        assert result == 0

    def test_empty(self):
        result = drawdown_duration(pd.Series(dtype=float))
        assert result == 0
