"""Full quantitative regression suite.

Integration tests that verify mathematical correctness and invariants.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from shared.models import AnalysisContext, MetricResult
from shared.analytics.returns import (
    price_returns, total_returns, log_returns,
    cumulative_return, annualized_return, annualized_volatility,
)
from shared.analytics.portfolio import Holding, Portfolio, portfolio_summary
from shared.analytics.nav import Position, build_historical_nav, nav_returns
from shared.analytics.volatility import (
    realized_volatility, parkinson_volatility, garman_klass_volatility,
    semi_deviation, portfolio_volatility, diversification_ratio,
)
from shared.analytics.risk import (
    historical_var, parametric_var, modified_var, portfolio_var,
)
from shared.analytics.performance import (
    linear_regression, tracking_error, information_ratio,
    sharpe_ratio, sortino_ratio, performance_attribution,
)
from shared.analytics.drawdown import (
    drawdown_series, max_drawdown, max_drawdown_with_dates,
    drawdown_periods, current_drawdown, drawdown_duration,
)
from shared.analytics.missing_data import (
    check_data_quality, validate_returns, validate_prices, DataQuality,
)


# ─── Test Data ────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_prices() -> pd.Series:
    """Sample price series for testing."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=252, freq="B")
    returns = np.random.normal(0.0005, 0.02, 252)
    prices = 100 * np.cumprod(1 + returns)
    return pd.Series(prices, index=dates)


@pytest.fixture
def sample_returns() -> pd.Series:
    """Sample return series for testing."""
    np.random.seed(42)
    return pd.Series(np.random.normal(0.0005, 0.02, 252))


@pytest.fixture
def sample_benchmark() -> pd.Series:
    """Sample benchmark returns."""
    np.random.seed(123)
    return pd.Series(np.random.normal(0.0003, 0.015, 252))


@pytest.fixture
def sample_matrix() -> pd.DataFrame:
    """Sample returns matrix for portfolio tests."""
    np.random.seed(42)
    return pd.DataFrame({
        "A": np.random.normal(0.001, 0.02, 252),
        "B": np.random.normal(0.0005, 0.03, 252),
        "C": np.random.normal(0.0008, 0.025, 252),
    })


# ─── AnalysisContext Tests ────────────────────────────────────────────────────

class TestAnalysisContext:
    """Test AnalysisContext invariants."""

    def test_creation(self):
        ctx = AnalysisContext(
            start_date="2024-01-01",
            end_date="2024-12-31",
            risk_free_rate=0.05,
        )
        assert ctx.risk_free_rate == 0.05
        assert ctx.periods_per_year == 252

    def test_immutability(self):
        ctx = AnalysisContext(risk_free_rate=0.05)
        with pytest.raises(Exception):
            ctx.risk_free_rate = 0.10


# ─── Returns Invariants ──────────────────────────────────────────────────────

class TestReturnsInvariants:
    """Test mathematical invariants for returns."""

    def test_price_returns_length(self, sample_prices):
        returns = price_returns(sample_prices)
        assert len(returns) == len(sample_prices)

    def test_price_returns_first_nan(self, sample_prices):
        returns = price_returns(sample_prices)
        assert returns.iloc[0] != returns.iloc[0]  # NaN check

    def test_log_returns_symmetry(self):
        prices = pd.Series([100, 110])
        returns = log_returns(prices)
        # log(110/100) = -log(100/110)
        assert abs(returns.iloc[1] - (-log_returns(pd.Series([110, 100])).iloc[1])) < 1e-10

    def test_cumulative_return_compounding(self, sample_prices):
        returns = price_returns(sample_prices)
        cum = cumulative_return(returns)
        # Cumulative return should match price ratio
        expected = sample_prices.iloc[-1] / sample_prices.iloc[0] - 1
        assert abs(cum.iloc[-1] - expected) < 1e-10


# ─── Volatility Invariants ───────────────────────────────────────────────────

class TestVolatilityInvariants:
    """Test mathematical invariants for volatility."""

    def test_volatility_positive(self, sample_returns):
        result = realized_volatility(sample_returns)
        assert result.value > 0

    def test_portfolio_vol_diversification(self, sample_matrix):
        """Diversification ratio > 1 for uncorrelated assets."""
        weights = np.array([1/3, 1/3, 1/3])
        dr = diversification_ratio(sample_matrix, weights)
        assert dr is not None
        assert dr > 1.0

    def test_perfect_correlation_no_diversification(self):
        """Perfectly correlated assets have DR = 1."""
        matrix = pd.DataFrame({
            "A": [0.01, -0.02, 0.015, -0.005],
            "B": [0.01, -0.02, 0.015, -0.005],
        })
        weights = np.array([0.5, 0.5])
        dr = diversification_ratio(matrix, weights)
        assert abs(dr - 1.0) < 1e-10


# ─── VaR Invariants ──────────────────────────────────────────────────────────

class TestVaRInvariants:
    """Test mathematical invariants for VaR."""

    def test_cvar_exceeds_var(self, sample_returns):
        result = historical_var(sample_returns, confidence=0.95)
        assert result.cvar >= result.var

    def test_higher_confidence_higher_var(self, sample_returns):
        var_95 = historical_var(sample_returns, confidence=0.95)
        var_99 = historical_var(sample_returns, confidence=0.99)
        assert var_99.var > var_95.var

    def test_horizon_scaling(self, sample_returns):
        var_1 = historical_var(sample_returns, horizon=1)
        var_10 = historical_var(sample_returns, horizon=10)
        # 10-day VaR should be ~sqrt(10) times 1-day VaR
        assert var_10.var > var_1.var


# ─── Performance Invariants ──────────────────────────────────────────────────

class TestPerformanceInvariants:
    """Test mathematical invariants for performance."""

    def test_sharpe_ratio_scaling(self, sample_returns):
        sr = sharpe_ratio(sample_returns, risk_free_rate=0.0)
        assert sr is not None

    def test_information_ratio_zero_active(self):
        """Zero active returns = zero IR."""
        returns = pd.Series([0.01] * 100)
        ir = information_ratio(returns, returns)
        assert ir is None  # Zero tracking error

    def test_beta_perfect_hedge(self):
        """Perfect hedge has beta = 1."""
        x = pd.Series([0.01, -0.02, 0.015, -0.005] * 25)
        y = x.copy()
        result = linear_regression(y, x)
        assert abs(result.beta - 1.0) < 1e-10


# ─── Drawdown Invariants ─────────────────────────────────────────────────────

class TestDrawdownInvariants:
    """Test mathematical invariants for drawdowns."""

    def test_drawdown_non_positive(self, sample_prices):
        dd = drawdown_series(sample_prices)
        assert (dd <= 0).all()

    def test_max_drawdown_negative(self, sample_prices):
        result = max_drawdown(sample_prices)
        assert result <= 0

    def test_monotonic_increase_no_drawdown(self):
        prices = pd.Series([100, 110, 120, 130, 140])
        result = max_drawdown(prices)
        assert result == 0.0


# ─── Portfolio Invariants ────────────────────────────────────────────────────

class TestPortfolioInvariants:
    """Test mathematical invariants for portfolios."""

    def test_weights_sum_to_one(self):
        p = Portfolio(
            name="Test",
            holdings=[
                Holding(ticker="A", quantity=100, average_cost=100.0, current_price=100.0),
                Holding(ticker="B", quantity=200, average_cost=200.0, current_price=200.0),
            ],
        )
        weights = p.current_weights()
        assert abs(sum(weights.values()) - 1.0) < 1e-10

    def test_cost_vs_current_weights(self):
        """Cost and current weights can differ."""
        p = Portfolio(
            name="Test",
            holdings=[
                Holding(ticker="A", quantity=100, average_cost=50.0, current_price=150.0),
                Holding(ticker="B", quantity=100, average_cost=150.0, current_price=50.0),
            ],
        )
        cost_w = p.cost_weights()
        current_w = p.current_weights()
        # Weights should be different
        assert cost_w["A"] != current_w["A"]


# ─── NAV Invariants ──────────────────────────────────────────────────────────

class TestNAVInvariants:
    """Test mathematical invariants for NAV."""

    def test_nav_components_sum_to_total(self):
        from datetime import date
        dates = [date(2024, 1, i) for i in range(1, 4)]

        pos_a = Position(
            ticker="A", quantity=100, buy_date=date(2024, 1, 1),
            prices=pd.Series([100, 110, 105], index=dates),
        )
        pos_b = Position(
            ticker="B", quantity=50, buy_date=date(2024, 1, 1),
            prices=pd.Series([200, 190, 210], index=dates),
        )
        nav = build_historical_nav([pos_a, pos_b])

        # Sum of components should equal total NAV
        for i in range(len(nav.dates)):
            component_sum = sum(comp[i] for comp in nav.components.values())
            assert abs(component_sum - nav.nav[i]) < 1e-10


# ─── Missing Data Invariants ─────────────────────────────────────────────────

class TestMissingDataInvariants:
    """Test invariants for missing data handling."""

    def test_quality_degrades_with_missing(self):
        complete = pd.Series(range(100))
        incomplete = pd.Series([1, 2, np.nan] * 33 + [1])

        q_complete = check_data_quality(complete, min_observations=30)
        q_incomplete = check_data_quality(incomplete, min_observations=30)

        assert q_complete.quality == DataQuality.COMPLETE
        assert q_incomplete.quality != DataQuality.COMPLETE

    def test_validation_extreme_returns(self):
        returns = pd.Series([0.01, -0.02, 0.6, -0.01])
        report = validate_returns(returns, min_observations=2)
        assert any("extreme" in w.lower() for w in report.warnings)


# ─── Integration Tests ────────────────────────────────────────────────────────

class TestIntegration:
    """Integration tests for full calculation pipeline."""

    def test_full_risk_analysis(self, sample_prices, sample_returns, sample_benchmark):
        """Test complete risk analysis pipeline."""
        # Returns
        returns = price_returns(sample_prices)
        assert len(returns) == len(sample_prices)

        # Volatility
        vol = realized_volatility(sample_returns)
        assert vol.value > 0

        # VaR
        var = historical_var(sample_returns, confidence=0.95)
        assert var.var > 0
        assert var.cvar >= var.var

        # Performance
        perf = performance_attribution(sample_returns, sample_benchmark)
        assert perf.beta is not None

        # Drawdown
        dd = drawdown_series(sample_prices)
        assert (dd <= 0).all()

    def test_portfolio_analysis(self):
        """Test complete portfolio analysis."""
        p = Portfolio(
            name="Test",
            holdings=[
                Holding(ticker="A", quantity=100, average_cost=100.0, current_price=120.0),
                Holding(ticker="B", quantity=50, average_cost=200.0, current_price=180.0),
            ],
        )

        # Summary
        summary = portfolio_summary(p)
        assert summary["total_market_value"] == 12000 + 9000
        assert summary["unrealized_pnl"] == (2000 + (-1000))

        # Weights
        weights = p.current_weights()
        assert abs(sum(weights.values()) - 1.0) < 1e-10
