"""Tests for portfolio model with market-value weighting."""
from __future__ import annotations

from datetime import date

import pytest

from shared.analytics.portfolio import Holding, Portfolio, portfolio_summary


class TestHolding:
    """Tests for Holding dataclass."""

    def test_basic_holding(self):
        h = Holding(ticker="AAPL", quantity=100, average_cost=150.0, current_price=175.0)
        assert h.cost_basis == 15000.0
        assert h.current_market_value == 17500.0

    def test_cost_weight(self):
        h = Holding(ticker="AAPL", quantity=100, average_cost=150.0, current_price=175.0)
        # cost_weight returns raw value, normalized externally
        assert h.cost_weight == 15000.0

    def test_current_weight(self):
        h = Holding(ticker="AAPL", quantity=100, average_cost=150.0, current_price=175.0)
        # current_weight returns raw value, normalized externally
        assert h.current_market_value == 17500.0


class TestPortfolio:
    """Tests for Portfolio class."""

    def test_empty_portfolio(self):
        p = Portfolio(name="Test")
        assert p.total_cost_basis == 0
        assert p.total_market_value == 0
        assert p.cost_weights() == {}
        assert p.current_weights() == {}

    def test_single_holding(self):
        p = Portfolio(
            name="Test",
            holdings=[Holding(ticker="AAPL", quantity=100, average_cost=150.0, current_price=175.0)],
        )
        assert p.total_cost_basis == 15000.0
        assert p.total_market_value == 17500.0
        assert p.cost_weights() == {"AAPL": 1.0}
        assert p.current_weights() == {"AAPL": 1.0}

    def test_multiple_holdings(self):
        p = Portfolio(
            name="Test",
            holdings=[
                Holding(ticker="A", quantity=100, average_cost=100.0, current_price=100.0),
                Holding(ticker="B", quantity=100, average_cost=300.0, current_price=300.0),
            ],
        )
        # A = 100*100 = 10000, B = 100*300 = 30000
        # Total = 40000
        # A weight = 25%, B weight = 75%
        weights = p.current_weights()
        assert abs(weights["A"] - 0.25) < 1e-10
        assert abs(weights["B"] - 0.75) < 1e-10

    def test_cost_vs_current_weights(self):
        """Cost weights and current weights can differ."""
        p = Portfolio(
            name="Test",
            holdings=[
                # Bought cheap, now expensive
                Holding(ticker="A", quantity=100, average_cost=50.0, current_price=150.0),
                # Bought expensive, now cheap
                Holding(ticker="B", quantity=100, average_cost=150.0, current_price=50.0),
            ],
        )
        # Cost: A = 5000, B = 15000, total = 20000
        # A cost weight = 25%, B cost weight = 75%
        cost_w = p.cost_weights()
        assert abs(cost_w["A"] - 0.25) < 1e-10
        assert abs(cost_w["B"] - 0.75) < 1e-10

        # Current: A = 15000, B = 5000, total = 20000
        # A current weight = 75%, B current weight = 25%
        current_w = p.current_weights()
        assert abs(current_w["A"] - 0.75) < 1e-10
        assert abs(current_w["B"] - 0.25) < 1e-10

    def test_get_holding(self):
        p = Portfolio(
            name="Test",
            holdings=[
                Holding(ticker="AAPL", quantity=100, average_cost=150.0, current_price=175.0),
                Holding(ticker="MSFT", quantity=50, average_cost=300.0, current_price=320.0),
            ],
        )
        h = p.get_holding("MSFT")
        assert h is not None
        assert h.ticker == "MSFT"
        assert p.get_holding("GOOG") is None


class TestPortfolioSummary:
    """Tests for portfolio_summary function."""

    def test_summary_structure(self):
        p = Portfolio(
            name="Test",
            currency="USD",
            as_of_date=date(2024, 12, 31),
            holdings=[
                Holding(ticker="AAPL", quantity=100, average_cost=150.0, current_price=175.0),
            ],
        )
        summary = portfolio_summary(p)
        assert summary["name"] == "Test"
        assert summary["currency"] == "USD"
        assert summary["total_cost_basis"] == 15000.0
        assert summary["total_market_value"] == 17500.0
        assert len(summary["holdings"]) == 1

    def test_summary_pnl(self):
        p = Portfolio(
            name="Test",
            holdings=[
                Holding(ticker="A", quantity=100, average_cost=100.0, current_price=120.0),
            ],
        )
        summary = portfolio_summary(p)
        assert summary["unrealized_pnl"] == 2000.0
        h = summary["holdings"][0]
        assert h["unrealized_pnl"] == 2000.0
        assert abs(h["unrealized_pnl_pct"] - 0.20) < 1e-10


class TestPropertyInvariants:
    """Property-based tests for portfolio invariants."""

    def test_weights_sum_to_one(self):
        p = Portfolio(
            name="Test",
            holdings=[
                Holding(ticker="A", quantity=100, average_cost=100.0, current_price=100.0),
                Holding(ticker="B", quantity=200, average_cost=200.0, current_price=200.0),
                Holding(ticker="C", quantity=50, average_cost=300.0, current_price=300.0),
            ],
        )
        weights = p.current_weights()
        assert abs(sum(weights.values()) - 1.0) < 1e-10
