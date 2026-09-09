"""Tests for dashboard helpers and metric provenance."""
from __future__ import annotations

import pytest

from shared.analytics.dashboard_helpers import (
    MetricDisplay,
    format_currency,
    format_percentage,
    format_number,
    metric_display_from_calculation,
    risk_metrics_display,
)


class TestFormatCurrency:
    """Tests for format_currency."""

    def test_basic(self):
        assert format_currency(1234.56) == "$1,234.56"

    def test_negative(self):
        assert format_currency(-1234.56) == "-$1,234.56"

    def test_euro(self):
        assert format_currency(1234.56, "EUR") == "€1,234.56"

    def test_gbp(self):
        assert format_currency(1234.56, "GBP") == "£1,234.56"

    def test_unknown_currency(self):
        assert format_currency(1234.56, "XYZ") == "XYZ 1,234.56"

    def test_zero(self):
        assert format_currency(0) == "$0.00"

    def test_decimals(self):
        assert format_currency(1234.567, decimals=3) == "$1,234.567"


class TestFormatPercentage:
    """Tests for format_percentage."""

    def test_basic(self):
        assert format_percentage(0.05) == "5.00%"

    def test_zero(self):
        assert format_percentage(0) == "0.00%"

    def test_negative(self):
        assert format_percentage(-0.05) == "-5.00%"

    def test_large(self):
        assert format_percentage(1.5) == "150.00%"


class TestFormatNumber:
    """Tests for format_number."""

    def test_basic(self):
        assert format_number(1234.56) == "1,234.56"

    def test_large(self):
        assert format_number(1234567.89) == "1,234,567.89"

    def test_negative(self):
        assert format_number(-1234.56) == "-1,234.56"


class TestMetricDisplayFromCalculation:
    """Tests for metric_display_from_calculation."""

    def test_none_value(self):
        result = metric_display_from_calculation("Test", None)
        assert result.value == "N/A"
        assert result.raw_value is None

    def test_currency_format(self):
        result = metric_display_from_calculation(
            "Value", 1234.56, currency="USD", format_func="currency",
        )
        assert result.value == "$1,234.56"
        assert result.currency == "USD"

    def test_percentage_format(self):
        result = metric_display_from_calculation(
            "Return", 0.05, unit="%", format_func="percentage",
        )
        assert result.value == "5.00%"
        assert result.unit == "%"

    def test_number_format(self):
        result = metric_display_from_calculation(
            "Ratio", 1.5, format_func="number",
        )
        assert result.value == "1.50"

    def test_auto_percentage(self):
        result = metric_display_from_calculation("Vol", 0.20, unit="%")
        assert result.value == "20.00%"

    def test_warnings(self):
        result = metric_display_from_calculation(
            "Test", 1.0, warnings=["Warning 1", "Warning 2"],
        )
        assert len(result.warnings) == 2


class TestRiskMetricsDisplay:
    """Tests for risk_metrics_display."""

    def test_basic(self):
        metrics = {
            "realized_volatility": 0.20,
            "sharpe_ratio": 1.5,
            "beta": 0.8,
        }
        displays = risk_metrics_display(metrics)
        assert len(displays) == 3
        names = [d.name for d in displays]
        assert "Realized Volatility" in names
        assert "Sharpe Ratio" in names
        assert "Beta" in names

    def test_unknown_metric(self):
        metrics = {"unknown_metric": 1.0}
        displays = risk_metrics_display(metrics)
        assert len(displays) == 0

    def test_none_values(self):
        metrics = {
            "realized_volatility": None,
            "sharpe_ratio": 1.5,
        }
        displays = risk_metrics_display(metrics)
        assert len(displays) == 2
        vol_display = [d for d in displays if d.name == "Realized Volatility"][0]
        assert vol_display.value == "N/A"
