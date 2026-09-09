"""Central configuration object for all analytical calculations.

Every quantitative function receives an AnalysisContext to ensure
consistent assumptions across related metrics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class AnalysisContext:
    """Configuration for quantitative analysis.

    Attributes:
        start_date: Analysis start date (None = earliest available).
        end_date: Analysis end date (None = latest available).
        frequency: Return frequency ("1d", "1w", "1m").
        return_type: Return methodology ("total" for adjusted, "price" for unadjusted).
        benchmark: Ticker symbol for benchmark (None = no benchmark).
        risk_free_rate: Annual risk-free rate as decimal (e.g., 0.05 = 5%).
        periods_per_year: Trading periods per year for annualization.
        currency: Portfolio currency (None = no currency constraint).
        min_observations: Minimum observations required for valid calculation.
        ddof: Degrees of freedom for standard deviation (1 for sample, 0 for population).
    """

    start_date: date | None = None
    end_date: date | None = None
    frequency: str = "1d"
    return_type: str = "total"
    benchmark: str | None = "SPY"
    risk_free_rate: float = 0.05
    periods_per_year: int = 252
    currency: str | None = None
    min_observations: int = 30
    ddof: int = 1

    def with_updates(self, **kwargs) -> AnalysisContext:
        """Return a new context with specified fields overridden."""
        return AnalysisContext(**{**self.__dict__, **kwargs})
