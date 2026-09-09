"""Tests for AnalysisContext and MetricResult models."""
from __future__ import annotations

from datetime import date

from shared.models import AnalysisContext, MetricResult


class TestAnalysisContext:
    """Tests for AnalysisContext configuration object."""

    def test_default_context(self):
        ctx = AnalysisContext()
        assert ctx.start_date is None
        assert ctx.end_date is None
        assert ctx.frequency == "1d"
        assert ctx.return_type == "total"
        assert ctx.benchmark == "SPY"
        assert ctx.risk_free_rate == 0.05
        assert ctx.periods_per_year == 252
        assert ctx.currency is None
        assert ctx.min_observations == 30
        assert ctx.ddof == 1

    def test_custom_context(self):
        ctx = AnalysisContext(
            start_date=date(2020, 1, 1),
            end_date=date(2024, 12, 31),
            benchmark="QQQ",
            risk_free_rate=0.04,
            periods_per_year=252,
            currency="USD",
        )
        assert ctx.start_date == date(2020, 1, 1)
        assert ctx.benchmark == "QQQ"
        assert ctx.risk_free_rate == 0.04
        assert ctx.currency == "USD"

    def test_frozen(self):
        ctx = AnalysisContext()
        try:
            ctx.benchmark = "QQQ"  # type: ignore
            assert False, "Should be frozen"
        except AttributeError:
            pass

    def test_with_updates(self):
        ctx = AnalysisContext(benchmark="SPY", risk_free_rate=0.05)
        ctx2 = ctx.with_updates(benchmark="QQQ")
        assert ctx2.benchmark == "QQQ"
        assert ctx2.risk_free_rate == 0.05
        assert ctx.benchmark == "SPY"  # original unchanged


class TestMetricResult:
    """Tests for MetricResult data object."""

    def test_available_result(self):
        result = MetricResult(
            name="sharpe_ratio",
            value=1.42,
            status="ok",
            observations=1247,
        )
        assert result.is_available
        assert result.value == 1.42

    def test_unavailable_result(self):
        result = MetricResult(
            name="beta",
            value=None,
            status="insufficient_data",
            observations=5,
        )
        assert not result.is_available
        assert result.value is None

    def test_summary_line(self):
        result = MetricResult(
            name="volatility",
            value=0.25,
            start_date=date(2020, 1, 1),
            end_date=date(2024, 12, 31),
            observations=1247,
            frequency="1d",
            return_type="total",
            risk_free_rate=0.048,
        )
        summary = result.summary_line()
        assert "2020" in summary
        assert "2024" in summary
        assert "1247" in summary
        assert "4.8%" in summary

    def test_warnings(self):
        result = MetricResult(
            name="alpha",
            value=0.02,
            warnings=["Insufficient benchmark overlap"],
        )
        assert len(result.warnings) == 1
        assert "benchmark" in result.warnings[0].lower()
