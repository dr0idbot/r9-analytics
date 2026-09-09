"""Tests for historical portfolio NAV reconstruction."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from shared.analytics.nav import (
    Position,
    NAVTimeSeries,
    build_historical_nav,
    nav_returns,
    component_contributions,
)


def _make_prices(dates: list[date], values: list[float]) -> pd.Series:
    """Helper to create a price series."""
    return pd.Series(values, index=dates, dtype=float)


class TestPosition:
    """Tests for Position dataclass."""

    def test_basic_position(self):
        p = Position(
            ticker="AAPL",
            quantity=100,
            buy_date=date(2024, 1, 1),
            prices=_make_prices([date(2024, 1, 1), date(2024, 1, 2)], [150.0, 155.0]),
        )
        assert p.ticker == "AAPL"
        assert p.quantity == 100
        assert len(p.prices) == 2


class TestBuildHistoricalNav:
    """Tests for build_historical_nav."""

    def test_empty_positions(self):
        result = build_historical_nav([])
        assert len(result.dates) == 0
        assert len(result.nav) == 0
        assert result.components == {}

    def test_single_position(self):
        dates = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]
        pos = Position(
            ticker="AAPL",
            quantity=100,
            buy_date=date(2024, 1, 1),
            prices=_make_prices(dates, [150.0, 160.0, 155.0]),
        )
        result = build_historical_nav([pos])

        assert len(result.dates) == 3
        np.testing.assert_allclose(result.nav, [15000.0, 16000.0, 15500.0])
        assert "AAPL" in result.components
        np.testing.assert_allclose(result.components["AAPL"], result.nav)

    def test_two_positions(self):
        dates_a = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]
        dates_b = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]

        pos_a = Position(
            ticker="A",
            quantity=100,
            buy_date=date(2024, 1, 1),
            prices=_make_prices(dates_a, [100.0, 110.0, 105.0]),
        )
        pos_b = Position(
            ticker="B",
            quantity=50,
            buy_date=date(2024, 1, 1),
            prices=_make_prices(dates_b, [200.0, 190.0, 210.0]),
        )
        result = build_historical_nav([pos_a, pos_b])

        # A: 100*100=10000, 100*110=11000, 100*105=10500
        # B: 50*200=10000, 50*190=9500, 50*210=10500
        # Total: 20000, 20500, 21000
        np.testing.assert_allclose(result.nav, [20000.0, 20500.0, 21000.0])

    def test_position_buy_later(self):
        """Position bought after start date contributes 0 before buy."""
        dates = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]

        pos_a = Position(
            ticker="A",
            quantity=100,
            buy_date=date(2024, 1, 1),
            prices=_make_prices(dates, [100.0, 100.0, 100.0]),
        )
        pos_b = Position(
            ticker="B",
            quantity=50,
            buy_date=date(2024, 1, 3),  # Bought on day 3
            prices=_make_prices(dates, [200.0, 200.0, 200.0]),
        )
        result = build_historical_nav([pos_a, pos_b])

        # Day 1: A only = 10000
        # Day 2: A only = 10000
        # Day 3: A + B = 10000 + 10000 = 20000
        np.testing.assert_allclose(result.nav, [10000.0, 10000.0, 20000.0])

    def test_weights_sum_to_one(self):
        dates = [date(2024, 1, 1), date(2024, 1, 2)]

        pos_a = Position(
            ticker="A",
            quantity=100,
            buy_date=date(2024, 1, 1),
            prices=_make_prices(dates, [100.0, 110.0]),
        )
        pos_b = Position(
            ticker="B",
            quantity=50,
            buy_date=date(2024, 1, 1),
            prices=_make_prices(dates, [200.0, 190.0]),
        )
        result = build_historical_nav([pos_a, pos_b])

        # Weights should sum to 1
        row_sums = result.weights.sum(axis=1)
        np.testing.assert_allclose(row_sums.values, [1.0, 1.0])

    def test_start_end_date_filter(self):
        dates = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
        pos = Position(
            ticker="A",
            quantity=100,
            buy_date=date(2024, 1, 1),
            prices=_make_prices(dates, [100.0, 110.0, 105.0, 115.0]),
        )
        result = build_historical_nav([pos], start_date=date(2024, 1, 2), end_date=date(2024, 1, 3))
        assert len(result.dates) == 2
        np.testing.assert_allclose(result.nav, [11000.0, 10500.0])

    def test_no_prices(self):
        pos = Position(ticker="A", quantity=100, buy_date=date(2024, 1, 1), prices=pd.Series(dtype=float))
        result = build_historical_nav([pos])
        assert len(result.dates) == 0


class TestNavReturns:
    """Tests for nav_returns."""

    def test_basic_returns(self):
        nav = NAVTimeSeries(
            dates=np.array([date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]),
            nav=np.array([100.0, 110.0, 105.0]),
            components={},
            weights=pd.DataFrame(),
        )
        returns = nav_returns(nav)
        assert len(returns) == 2
        assert abs(returns.iloc[0] - 0.10) < 1e-10
        assert abs(returns.iloc[1] - (-5 / 110)) < 1e-10

    def test_empty_nav(self):
        nav = NAVTimeSeries(dates=np.array([]), nav=np.array([]), components={}, weights=pd.DataFrame())
        returns = nav_returns(nav)
        assert len(returns) == 0

    def test_single_date(self):
        nav = NAVTimeSeries(
            dates=np.array([date(2024, 1, 1)]),
            nav=np.array([100.0]),
            components={},
            weights=pd.DataFrame(),
        )
        returns = nav_returns(nav)
        assert len(returns) == 0


class TestComponentContributions:
    """Tests for component_contributions."""

    def test_basic_contributions(self):
        dates = np.array([date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)])

        # A: 10000 -> 11000 -> 10500
        # B: 10000 -> 9500 -> 10500
        # Total: 20000 -> 20500 -> 21000

        nav = NAVTimeSeries(
            dates=dates,
            nav=np.array([20000.0, 20500.0, 21000.0]),
            components={
                "A": np.array([10000.0, 11000.0, 10500.0]),
                "B": np.array([10000.0, 9500.0, 10500.0]),
            },
            weights=pd.DataFrame(),
        )
        contrib = component_contributions(nav)
        assert len(contrib) == 2
        assert "A" in contrib.columns
        assert "B" in contrib.columns

    def test_empty_nav(self):
        nav = NAVTimeSeries(dates=np.array([]), nav=np.array([]), components={}, weights=pd.DataFrame())
        contrib = component_contributions(nav)
        assert len(contrib) == 0
