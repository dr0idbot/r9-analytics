"""Portfolio model with correct market-value weighting.

Separates cost basis from market exposure.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from shared.models import AnalysisContext, MetricResult

logger = logging.getLogger(__name__)


@dataclass
class Holding:
    """Single portfolio holding.

    Attributes:
        ticker: Security ticker symbol.
        quantity: Number of shares held.
        average_cost: Average cost per share (cost basis).
        current_price: Current market price per share.
        currency: Currency of the security.
    """

    ticker: str
    quantity: float
    average_cost: float
    current_price: float
    currency: str | None = None

    @property
    def cost_basis(self) -> float:
        """Total cost basis: quantity × average_cost."""
        return self.quantity * self.average_cost

    @property
    def current_market_value(self) -> float:
        """Current market value: quantity × current_price."""
        return self.quantity * self.current_price

    @property
    def cost_weight(self) -> float:
        """Weight based on cost basis (for cost allocation reporting)."""
        return self.cost_basis  # Normalized externally

    @property
    def current_weight(self) -> float:
        """Weight based on current market value (for risk exposure)."""
        return self.current_market_value  # Normalized externally


@dataclass
class Portfolio:
    """Portfolio with multiple holdings.

    Attributes:
        name: Portfolio name.
        currency: Portfolio base currency.
        holdings: List of Holding objects.
        as_of_date: Date of current prices.
    """

    name: str
    currency: str | None = None
    holdings: list[Holding] = field(default_factory=list)
    as_of_date: date | None = None

    @property
    def total_cost_basis(self) -> float:
        """Sum of all cost bases."""
        return sum(h.cost_basis for h in self.holdings)

    @property
    def total_market_value(self) -> float:
        """Sum of all current market values."""
        return sum(h.current_market_value for h in self.holdings)

    def cost_weights(self) -> dict[str, float]:
        """Compute weights based on cost basis.

        Returns:
            Dict mapping ticker to cost weight.
        """
        total = self.total_cost_basis
        if total == 0:
            return {h.ticker: 0.0 for h in self.holdings}
        return {h.ticker: h.cost_basis / total for h in self.holdings}

    def current_weights(self) -> dict[str, float]:
        """Compute weights based on current market value.

        This is the correct measure for risk exposure.

        Returns:
            Dict mapping ticker to current weight.
        """
        total = self.total_market_value
        if total == 0:
            return {h.ticker: 0.0 for h in self.holdings}
        return {h.ticker: h.current_market_value / total for h in self.holdings}

    def get_holding(self, ticker: str) -> Holding | None:
        """Get holding by ticker."""
        for h in self.holdings:
            if h.ticker == ticker:
                return h
        return None


def portfolio_summary(portfolio: Portfolio) -> dict:
    """Generate portfolio summary with both cost and market weights.

    Args:
        portfolio: Portfolio object.

    Returns:
        Dict with portfolio summary including weights.
    """
    cost_w = portfolio.cost_weights()
    current_w = portfolio.current_weights()

    holdings_summary = []
    for h in portfolio.holdings:
        holdings_summary.append({
            "ticker": h.ticker,
            "quantity": h.quantity,
            "average_cost": h.average_cost,
            "current_price": h.current_price,
            "cost_basis": h.cost_basis,
            "market_value": h.current_market_value,
            "cost_weight": cost_w.get(h.ticker, 0.0),
            "current_weight": current_w.get(h.ticker, 0.0),
            "unrealized_pnl": h.current_market_value - h.cost_basis,
            "unrealized_pnl_pct": (
                (h.current_price / h.average_cost - 1)
                if h.average_cost > 0
                else 0.0
            ),
        })

    return {
        "name": portfolio.name,
        "currency": portfolio.currency,
        "as_of_date": portfolio.as_of_date,
        "total_cost_basis": portfolio.total_cost_basis,
        "total_market_value": portfolio.total_market_value,
        "unrealized_pnl": portfolio.total_market_value - portfolio.total_cost_basis,
        "holdings": holdings_summary,
    }
