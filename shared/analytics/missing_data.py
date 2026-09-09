"""Missing data handling and data quality checks.

Explicit behavior for insufficient data, NaN handling, and quality gates.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class DataQuality(Enum):
    """Data quality status."""

    COMPLETE = "complete"
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    MISSING = "missing"


@dataclass
class DataQualityReport:
    """Report on data quality for a calculation.

    Attributes:
        quality: Overall quality status.
        total_observations: Total observations available.
        valid_observations: Non-NaN observations.
        missing_count: Number of missing values.
        missing_pct: Percentage of missing values.
        min_required: Minimum observations required.
        warnings: List of quality warnings.
    """

    quality: DataQuality
    total_observations: int
    valid_observations: int
    missing_count: int
    missing_pct: float
    min_required: int
    warnings: list[str] = field(default_factory=list)


@dataclass
class CalculationResult:
    """Result of a calculation with quality metadata.

    Attributes:
        value: The calculated value (None if insufficient data).
        quality: Data quality report.
        warnings: Calculation-specific warnings.
    """

    value: float | dict | list | None
    quality: DataQualityReport
    warnings: list[str] = field(default_factory=list)


def check_data_quality(
    data: pd.Series | pd.DataFrame,
    min_observations: int = 30,
    name: str = "data",
) -> DataQualityReport:
    """Check data quality for a calculation.

    Args:
        data: Input data (Series or DataFrame).
        min_observations: Minimum observations required.
        name: Name of the data for warnings.

    Returns:
        DataQualityReport with quality assessment.
    """
    if isinstance(data, pd.DataFrame):
        total = len(data)
        valid = data.dropna()
        valid_count = len(valid)
        missing_count = total - valid_count
    else:
        total = len(data)
        valid_count = data.count()
        missing_count = total - valid_count

    missing_pct = (missing_count / total * 100) if total > 0 else 0.0

    warnings = []
    if missing_pct > 0:
        warnings.append(f"{name} has {missing_pct:.1f}% missing values ({missing_count}/{total})")

    if valid_count < min_observations:
        warnings.append(f"{name} has {valid_count} valid observations, minimum required is {min_observations}")

    # Determine quality
    if total == 0:
        quality = DataQuality.MISSING
    elif valid_count < min_observations:
        quality = DataQuality.INSUFFICIENT
    elif missing_pct > 10:
        quality = DataQuality.SUFFICIENT  # Has enough but with warnings
    else:
        quality = DataQuality.COMPLETE

    return DataQualityReport(
        quality=quality,
        total_observations=total,
        valid_observations=valid_count,
        missing_count=missing_count,
        missing_pct=missing_pct,
        min_required=min_observations,
        warnings=warnings,
    )


def validate_returns(
    returns: pd.Series,
    min_observations: int = 30,
    name: str = "returns",
) -> DataQualityReport:
    """Validate return series for calculations.

    Args:
        returns: Return series.
        min_observations: Minimum observations required.
        name: Name for warnings.

    Returns:
        DataQualityReport with validation results.
    """
    report = check_data_quality(returns, min_observations, name)

    # Additional checks for returns
    if report.quality != DataQuality.MISSING:
        clean = returns.dropna()
        if len(clean) > 0:
            # Check for extreme returns
            max_return = clean.max()
            min_return = clean.min()
            if abs(max_return) > 0.5:
                report.warnings.append(f"{name} has extreme positive return: {max_return:.2%}")
            if abs(min_return) > 0.5:
                report.warnings.append(f"{name} has extreme negative return: {min_return:.2%}")

            # Check for constant returns (very low variance)
            std = clean.std()
            if std < 1e-10:
                report.warnings.append(f"{name} has near-zero variance (constant returns)")

    return report


def validate_prices(
    prices: pd.Series,
    min_observations: int = 30,
    name: str = "prices",
) -> DataQualityReport:
    """Validate price series for calculations.

    Args:
        prices: Price series.
        min_observations: Minimum observations required.
        name: Name for warnings.

    Returns:
        DataQualityReport with validation results.
    """
    report = check_data_quality(prices, min_observations, name)

    # Additional checks for prices
    if report.quality != DataQuality.MISSING:
        clean = prices.dropna()
        if len(clean) > 0:
            # Check for negative prices
            if (clean < 0).any():
                report.warnings.append(f"{name} contains negative values")

            # Check for zero prices
            if (clean == 0).any():
                report.warnings.append(f"{name} contains zero values")

            # Check for non-monotonic (could indicate data issues)
            if len(clean) > 1:
                pct_change = clean.pct_change().dropna()
                if (pct_change < -0.5).any():
                    report.warnings.append(f"{name} has large downward moves (>50%)")

    return report


def validate_matrix(
    matrix: pd.DataFrame,
    min_observations: int = 30,
    name: str = "returns_matrix",
) -> DataQualityReport:
    """Validate returns matrix for portfolio calculations.

    Args:
        matrix: Returns matrix with assets as columns.
        min_observations: Minimum observations required.
        name: Name for warnings.

    Returns:
        DataQualityReport with validation results.
    """
    report = check_data_quality(matrix, min_observations, name)

    # Additional checks for matrix
    if report.quality != DataQuality.MISSING:
        # Check each column
        for col in matrix.columns:
            col_report = check_data_quality(matrix[col], min_observations, f"{name}.{col}")
            report.warnings.extend(col_report.warnings)

        # Check for perfect correlation
        if len(matrix.columns) > 1:
            clean = matrix.dropna()
            if len(clean) > 1:
                corr = clean.corr()
                for i in range(len(corr.columns)):
                    for j in range(i + 1, len(corr.columns)):
                        if abs(corr.iloc[i, j]) > 0.99:
                            report.warnings.append(
                                f"{name}: {corr.columns[i]} and {corr.columns[j]} are nearly perfectly correlated"
                            )

    return report


def require_minimum_data(
    data: pd.Series | pd.DataFrame,
    min_observations: int = 30,
    name: str = "data",
) -> None:
    """Raise ValueError if data is insufficient.

    Args:
        data: Input data.
        min_observations: Minimum required.
        name: Name for error message.

    Raises:
        ValueError: If insufficient data.
    """
    report = check_data_quality(data, min_observations, name)
    if report.quality == DataQuality.INSUFFICIENT:
        raise ValueError(
            f"Insufficient data for {name}: {report.valid_observations} observations, "
            f"minimum required is {min_observations}"
        )
    if report.quality == DataQuality.MISSING:
        raise ValueError(f"No data available for {name}")
