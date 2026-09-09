"""Dashboard helpers for currency handling and metric provenance.

Displays metrics with proper currency formatting and calculation metadata.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class MetricDisplay:
    """Display-ready metric with provenance.

    Attributes:
        name: Metric name.
        value: Formatted value string.
        raw_value: Original numeric value.
        unit: Unit of measurement.
        currency: Currency if applicable.
        method: Calculation method.
        source: Data source.
        timestamp: When calculated.
        warnings: Any warnings about the metric.
    """

    name: str
    value: str
    raw_value: float | None
    unit: str
    currency: str | None = None
    method: str | None = None
    source: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    warnings: list[str] = field(default_factory=list)


# Currency symbols
CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "CHF": "CHF",
    "CAD": "C$",
    "AUD": "A$",
    "HKD": "HK$",
    "SGD": "S$",
}


def format_currency(value: float, currency: str = "USD", decimals: int = 2) -> str:
    """Format a value as currency.

    Args:
        value: Numeric value.
        currency: Currency code (e.g. "USD", "EUR").
        decimals: Decimal places.

    Returns:
        Formatted currency string.
    """
    symbol = CURRENCY_SYMBOLS.get(currency, currency + " ")
    if value < 0:
        return f"-{symbol}{abs(value):,.{decimals}f}"
    return f"{symbol}{value:,.{decimals}f}"


def format_percentage(value: float, decimals: int = 2) -> str:
    """Format a value as percentage.

    Args:
        value: Numeric value (e.g. 0.05 for 5%).
        decimals: Decimal places.

    Returns:
        Formatted percentage string.
    """
    return f"{value * 100:.{decimals}f}%"


def format_number(value: float, decimals: int = 2) -> str:
    """Format a number with thousand separators.

    Args:
        value: Numeric value.
        decimals: Decimal places.

    Returns:
        Formatted number string.
    """
    return f"{value:,.{decimals}f}"


def metric_display_from_calculation(
    name: str,
    value: float | None,
    unit: str = "",
    currency: str | None = None,
    method: str | None = None,
    source: str | None = None,
    warnings: list[str] | None = None,
    format_func: str | None = None,
) -> MetricDisplay:
    """Create MetricDisplay from calculation result.

    Args:
        name: Metric name.
        value: Raw value.
        unit: Unit of measurement.
        currency: Currency code.
        method: Calculation method.
        source: Data source.
        warnings: List of warnings.
        format_func: Formatting function name ("currency", "percentage", "number").

    Returns:
        MetricDisplay ready for dashboard.
    """
    if value is None:
        formatted = "N/A"
    elif format_func == "currency" and currency:
        formatted = format_currency(value, currency)
    elif format_func == "percentage":
        formatted = format_percentage(value)
    elif format_func == "number":
        formatted = format_number(value)
    elif unit == "%":
        formatted = format_percentage(value)
    elif currency:
        formatted = format_currency(value, currency)
    else:
        formatted = format_number(value)

    return MetricDisplay(
        name=name,
        value=formatted,
        raw_value=value,
        unit=unit,
        currency=currency,
        method=method,
        source=source,
        warnings=warnings or [],
    )


def risk_metrics_display(
    metrics: dict[str, float | None],
    currency: str = "USD",
) -> list[MetricDisplay]:
    """Format risk metrics for dashboard display.

    Args:
        metrics: Dict of metric name to value.
        currency: Currency for dollar metrics.

    Returns:
        List of MetricDisplay objects.
    """
    display_map = {
        "realized_volatility": ("Realized Volatility", "%", "percentage"),
        "semi_deviation": ("Semi-Deviation", "%", "percentage"),
        "parkinson_volatility": ("Parkinson Volatility", "%", "percentage"),
        "garman_klass_volatility": ("Garman-Klass Volatility", "%", "percentage"),
        "historical_var_95": ("Historical VaR (95%)", "%", "percentage"),
        "parametric_var_95": ("Parametric VaR (95%)", "%", "percentage"),
        "modified_var_95": ("Modified VaR (95%)", "%", "percentage"),
        "cvar_95": ("CVaR (95%)", "%", "percentage"),
        "max_drawdown": ("Max Drawdown", "%", "percentage"),
        "sharpe_ratio": ("Sharpe Ratio", "", "number"),
        "sortino_ratio": ("Sortino Ratio", "", "number"),
        "calmar_ratio": ("Calmar Ratio", "", "number"),
        "treynor_ratio": ("Treynor Ratio", "", "number"),
        "information_ratio": ("Information Ratio", "", "number"),
        "omega_ratio": ("Omega Ratio", "", "number"),
        "beta": ("Beta", "", "number"),
        "alpha": ("Alpha", "%", "percentage"),
        "r_squared": ("R-Squared", "", "number"),
        "tracking_error": ("Tracking Error", "%", "percentage"),
    }

    displays = []
    for key, value in metrics.items():
        if key in display_map:
            name, unit, fmt = display_map[key]
            displays.append(metric_display_from_calculation(
                name=name,
                value=value,
                unit=unit,
                format_func=fmt,
            ))

    return displays
