"""Standardized result object for quantitative metrics.

Every major calculation returns a MetricResult that includes
the value, metadata about how it was computed, and any warnings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class MetricResult:
    """Result of a quantitative metric calculation.

    Attributes:
        name: Metric name (e.g., "sharpe_ratio").
        value: Computed value (None if unavailable).
        status: "ok", "unavailable", "insufficient_data", "error".
        start_date: Start of observation window used.
        end_date: End of observation window used.
        observations: Number of observations used.
        frequency: Return frequency used.
        return_type: Return methodology used.
        benchmark: Benchmark ticker if applicable.
        risk_free_rate: Risk-free rate used if applicable.
        periods_per_year: Annualization factor used.
        methodology: Brief description of calculation method.
        warnings: List of data-quality or methodology warnings.
        details: Additional key-value pairs for UI display.
    """

    name: str
    value: float | None = None
    status: str = "ok"
    start_date: date | None = None
    end_date: date | None = None
    observations: int = 0
    frequency: str = "1d"
    return_type: str = "total"
    benchmark: str | None = None
    risk_free_rate: float | None = None
    periods_per_year: int = 252
    methodology: str = ""
    warnings: list[str] = field(default_factory=list)
    details: dict[str, str | float | int] = field(default_factory=dict)

    @property
    def is_available(self) -> bool:
        """True if the metric was successfully computed."""
        return self.status == "ok" and self.value is not None

    def summary_line(self) -> str:
        """One-line summary for UI display."""
        parts = []
        if self.start_date and self.end_date:
            parts.append(f"{self.start_date} to {self.end_date}")
        if self.observations:
            parts.append(f"{self.observations} obs")
        if self.frequency:
            parts.append(self.frequency)
        if self.return_type:
            parts.append(f"{self.return_type} return")
        if self.risk_free_rate is not None:
            parts.append(f"RF: {self.risk_free_rate:.1%}")
        return " | ".join(parts) if parts else self.methodology
