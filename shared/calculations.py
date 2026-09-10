"""Portfolio exposure and risk calculations.

Computes sector/industry exposure and single-asset risk metrics.
All functions accept a psycopg Connection — no global state.

Corrected quantitative methodology:
- VaR uses true multi-period historical returns (not sqrt scaling)
- Sharpe/Sortino use periodic excess returns
- Diversification ratio divides by portfolio vol (not /100)
- Returns None for missing/insufficient data (not 0.0)
- Risk-free rate is configurable per call
- Portfolio weights align with available data
"""
from __future__ import annotations

import logging
from datetime import date, datetime

import numpy as np
import pandas as pd
import psycopg

from shared.db import (
    ensure_calc_schema,
    get_latest_portfolio_risk,
    get_latest_risk_metrics,
    get_portfolio as _get_portfolio,
    get_portfolio_securities,
    insert_portfolio_risk,
    insert_risk_metrics,
)
from shared.queries import get_candles_df

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252
DEFAULT_RISK_FREE_RATE = 0.05  # 5% annual default — overridable per call


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #

def _validate_confidence(confidence: float) -> None:
    if not (0 < confidence < 1):
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")


def _validate_horizon(horizon: int) -> None:
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")


def _validate_period(period: str) -> None:
    if period not in ("daily", "weekly", "monthly"):
        raise ValueError(f"period must be 'daily', 'weekly', or 'monthly', got '{period}'")


# --------------------------------------------------------------------------- #
# Portfolio exposure (sector / industry)
# --------------------------------------------------------------------------- #

def portfolio_sector_exposure(conn: psycopg.Connection, portfolio_id: int) -> list[dict]:
    """Compute sector exposure for a portfolio.

    Groups securities by sector and sums their cost-basis market values,
    then converts to weights.

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.

    Returns:
        List of dicts sorted by weight descending.

    Raises:
        ValueError: If portfolio not found.
    """
    portfolio = _get_portfolio(conn, portfolio_id)
    if portfolio is None:
        raise ValueError(f"Portfolio id {portfolio_id} not found")

    securities = get_portfolio_securities(conn, portfolio_id)
    total_value = sum(s["buy_price"] * s["units"] for s in securities)

    if total_value == 0:
        return []

    sector_map: dict[str, dict] = {}
    for sec in securities:
        sector = sec["sector"] or "Unknown"
        market_value = sec["buy_price"] * sec["units"]
        if sector not in sector_map:
            sector_map[sector] = {"sector": sector, "weight": 0.0, "tickers": []}
        sector_map[sector]["weight"] += market_value / total_value
        sector_map[sector]["tickers"].append(sec["ticker"])

    result = sorted(sector_map.values(), key=lambda x: x["weight"], reverse=True)
    logger.info(
        "Sector exposure for portfolio '%s': %d sectors",
        portfolio["name"], len(result),
    )
    return result


def portfolio_industry_exposure(conn: psycopg.Connection, portfolio_id: int) -> list[dict]:
    """Compute industry exposure for a portfolio.

    Groups securities by industry and sums their cost-basis market values,
    then converts to weights.

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.

    Returns:
        List of dicts sorted by weight descending.

    Raises:
        ValueError: If portfolio not found.
    """
    portfolio = _get_portfolio(conn, portfolio_id)
    if portfolio is None:
        raise ValueError(f"Portfolio id {portfolio_id} not found")

    securities = get_portfolio_securities(conn, portfolio_id)
    total_value = sum(s["buy_price"] * s["units"] for s in securities)

    if total_value == 0:
        return []

    industry_map: dict[str, dict] = {}
    for sec in securities:
        industry = sec["industry"] or "Unknown"
        market_value = sec["buy_price"] * sec["units"]
        if industry not in industry_map:
            industry_map[industry] = {"industry": industry, "weight": 0.0, "tickers": []}
        industry_map[industry]["weight"] += market_value / total_value
        industry_map[industry]["tickers"].append(sec["ticker"])

    result = sorted(industry_map.values(), key=lambda x: x["weight"], reverse=True)
    logger.info(
        "Industry exposure for portfolio '%s': %d industries",
        portfolio["name"], len(result),
    )
    return result


def portfolio_exposure(conn: psycopg.Connection, portfolio_id: int) -> dict:
    """Compute both sector and industry exposure for a portfolio.

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.

    Returns:
        Dict with "sector" and "industry" keys.
    """
    return {
        "sector": portfolio_sector_exposure(conn, portfolio_id),
        "industry": portfolio_industry_exposure(conn, portfolio_id),
    }


# --------------------------------------------------------------------------- #
# Data retrieval helpers
# --------------------------------------------------------------------------- #

def daily_returns(
    conn: psycopg.Connection,
    ticker: str,
    start_date: date | None = None,
    end_date: date | None = None,
    return_type: str = "close",
) -> pd.Series | None:
    """Compute daily simple returns from price data.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        start_date: Optional start date filter.
        end_date: Optional end date filter.
        return_type: "close" for price returns, "adj" for total returns.

    Returns:
        Series of daily returns, or None if insufficient data.
    """
    df = get_candles_df(conn, ticker, start_date, end_date)
    if df is None or df.empty or len(df) < 2:
        return None

    col = "adj_close" if return_type == "adj" else "close"
    if col not in df.columns:
        col = "close"

    returns = df[col].pct_change().dropna()
    if returns.empty:
        return None
    return returns


def _aligned_returns(
    conn: psycopg.Connection,
    tickers: list[str],
    return_type: str = "close",
) -> pd.DataFrame | None:
    """Fetch and align return series for multiple tickers.

    Returns DataFrame with columns = tickers, rows = common trading dates.
    Returns None if insufficient overlapping data.
    """
    dfs: dict[str, pd.Series] = {}
    for ticker in tickers:
        ret = daily_returns(conn, ticker, return_type=return_type)
        if ret is not None and not ret.empty:
            dfs[ticker] = ret

    if not dfs:
        return None

    result = pd.DataFrame(dfs)
    if result.empty:
        return None

    # Only keep rows where all tickers have data
    result = result.dropna(axis=0, how="any")
    if result.empty:
        return None

    return result


def _annualized_return_from_returns(returns: pd.Series) -> float | None:
    """Compute annualized return from a return series using geometric linking.

    Uses actual elapsed time (first to last observation) for annualization.
    """
    if returns is None or returns.empty or len(returns) < 2:
        return None

    # Cumulative return
    cumulative = (1 + returns).prod()
    if cumulative <= 0:
        return None

    # Estimate years from index
    if hasattr(returns.index, 'to_pydatetime'):
        dates = returns.index.to_pydatetime()
        if len(dates) >= 2:
            elapsed_days = (dates[-1] - dates[0]).days
            years = elapsed_days / 365.25
        else:
            years = len(returns) / TRADING_DAYS_PER_YEAR
    else:
        years = len(returns) / TRADING_DAYS_PER_YEAR

    if years <= 0:
        return None

    return float(cumulative ** (1 / years) - 1)


# --------------------------------------------------------------------------- #
# Phase 1 — Single-Asset Risk Metrics
# --------------------------------------------------------------------------- #

def realized_volatility(
    conn: psycopg.Connection,
    ticker: str,
    window: int | None = None,
    annualize: bool = True,
) -> float | None:
    """Compute realized volatility (standard deviation of returns).

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        window: If None, use all data. If int, use last N periods.
        annualize: If True, multiply by sqrt(252).

    Returns:
        Volatility as a decimal (e.g. 0.20 = 20%), or None if insufficient data.
    """
    returns = daily_returns(conn, ticker)
    if returns is None or returns.empty:
        return None

    if window is not None:
        returns = returns.tail(window)

    if len(returns) < 2:
        return None

    vol = returns.std(ddof=1)
    if annualize:
        vol *= np.sqrt(TRADING_DAYS_PER_YEAR)
    return float(vol)


def historical_var(
    conn: psycopg.Connection,
    ticker: str,
    confidence: float = 0.95,
    horizon: int = 1,
) -> float | None:
    """Compute Historical Value at Risk using true multi-period returns.

    For horizon > 1, aggregates rolling horizon-day returns rather than
    applying sqrt(horizon) scaling.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        confidence: Confidence level in (0, 1).
        horizon: Number of days for VaR projection (>= 1).

    Returns:
        VaR as a negative number (e.g. -0.03 means 3% loss), or None.
    """
    _validate_confidence(confidence)
    _validate_horizon(horizon)

    returns = daily_returns(conn, ticker)
    if returns is None or returns.empty:
        return None

    # True multi-period: compute rolling horizon-day returns
    if horizon > 1:
        # Need raw prices to compute multi-period returns correctly
        df = get_candles_df(conn, ticker)
        if df is None or df.empty or len(df) < horizon + 1:
            return None
        prices = df["close"]
        horizon_returns = prices.pct_change(horizon).dropna()
        if horizon_returns.empty:
            return None
        returns = horizon_returns

    min_obs = max(10, horizon)
    if len(returns) < min_obs:
        return None

    percentile = (1 - confidence) * 100
    var = np.percentile(returns, percentile)
    return float(var)


def parametric_var(
    conn: psycopg.Connection,
    ticker: str,
    confidence: float = 0.95,
    horizon: int = 1,
) -> float | None:
    """Compute Parametric VaR (variance-covariance method).

    Assumes normal distribution of returns.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        confidence: Confidence level in (0, 1).
        horizon: Number of days for VaR projection (>= 1).

    Returns:
        VaR as a negative number, or None.
    """
    _validate_confidence(confidence)
    _validate_horizon(horizon)

    returns = daily_returns(conn, ticker)
    if returns is None or returns.empty or len(returns) < 10:
        return None

    from scipy import stats

    mean = returns.mean()
    std = returns.std(ddof=1)

    # Scale for horizon
    if horizon > 1:
        mean *= horizon
        std *= np.sqrt(horizon)

    z_score = stats.norm.ppf(1 - confidence)
    var = mean + z_score * std
    return float(var)


def cvar(
    conn: psycopg.Connection,
    ticker: str,
    confidence: float = 0.95,
) -> float | None:
    """Compute Conditional VaR (Expected Shortfall).

    Mean of all returns that are worse than VaR.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        confidence: Confidence level in (0, 1).

    Returns:
        CVaR as a negative number (always worse than VaR), or None.
    """
    _validate_confidence(confidence)

    returns = daily_returns(conn, ticker)
    if returns is None or returns.empty or len(returns) < 10:
        return None

    var_threshold = historical_var(conn, ticker, confidence)
    if var_threshold is None:
        return None

    tail_returns = returns[returns <= var_threshold]
    if tail_returns.empty:
        return var_threshold
    return float(tail_returns.mean())


def parkinson_volatility(
    conn: psycopg.Connection,
    ticker: str,
    annualize: bool = True,
) -> float | None:
    """Compute Parkinson volatility using high/low price range.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        annualize: If True, multiply by sqrt(252).

    Returns:
        Parkinson volatility as a decimal, or None.
    """
    df = get_candles_df(conn, ticker)
    if df is None or df.empty or len(df) < 2:
        return None

    # Validate OHLC
    if not all(c in df.columns for c in ("high", "low")):
        return None

    mask = (df["high"] > 0) & (df["low"] > 0) & (df["high"] >= df["low"])
    df = df[mask]
    if len(df) < 2:
        return None

    log_hl = np.log(df["high"] / df["low"])
    parkinson_var = (log_hl ** 2).sum() / (4 * len(df) * np.log(2))
    vol = np.sqrt(parkinson_var)

    if annualize:
        vol *= np.sqrt(TRADING_DAYS_PER_YEAR)
    return float(vol)


def garman_klass_volatility(
    conn: psycopg.Connection,
    ticker: str,
    annualize: bool = True,
) -> float | None:
    """Compute Garman-Klass volatility using OHLC data.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        annualize: If True, multiply by sqrt(252).

    Returns:
        Garman-Klass volatility as a decimal, or None.
    """
    df = get_candles_df(conn, ticker)
    if df is None or df.empty or len(df) < 2:
        return None

    required = ("high", "low", "close", "open")
    if not all(c in df.columns for c in required):
        return None

    mask = (df["high"] > 0) & (df["low"] > 0) & (df["close"] > 0) & (df["open"] > 0)
    df = df[mask]
    if len(df) < 2:
        return None

    log_hl = np.log(df["high"] / df["low"])
    log_co = np.log(df["close"] / df["open"])

    gk_var = 0.5 * (log_hl ** 2).sum() - (2 * np.log(2) - 1) * (log_co ** 2).sum()
    gk_var /= len(df)
    vol = np.sqrt(max(gk_var, 0))

    if annualize:
        vol *= np.sqrt(TRADING_DAYS_PER_YEAR)
    return float(vol)


def max_drawdown(conn: psycopg.Connection, ticker: str) -> float | None:
    """Compute maximum drawdown from peak.

    Uses adjusted close for total-return drawdown.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.

    Returns:
        Maximum drawdown as a negative number, or None.
    """
    df = get_candles_df(conn, ticker)
    if df is None or df.empty or len(df) < 2:
        return None

    prices = df.get("adj_close", df["close"])
    cummax = prices.cummax()
    drawdown = (prices - cummax) / cummax
    return float(drawdown.min())


def semi_deviation(
    conn: psycopg.Connection,
    ticker: str,
    annualize: bool = True,
) -> float | None:
    """Compute semi-deviation (downside volatility).

    Uses the standard deviation of negative returns, annualized.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        annualize: If True, multiply by sqrt(252).

    Returns:
        Semi-deviation as a decimal, or None.
    """
    returns = daily_returns(conn, ticker)
    if returns is None or returns.empty:
        return None

    negative_returns = returns[returns < 0]
    if len(negative_returns) < 2:
        return None

    semi_vol = negative_returns.std(ddof=1)
    if annualize:
        semi_vol *= np.sqrt(TRADING_DAYS_PER_YEAR)
    return float(semi_vol)


def downside_ratio(conn: psycopg.Connection, ticker: str) -> float | None:
    """Compute downside ratio (semi-deviation / total volatility).

    Args:
        conn: Database connection.
        ticker: Ticker symbol.

    Returns:
        Ratio between 0 and 1, or None.
    """
    total_vol = realized_volatility(conn, ticker, annualize=False)
    semi_vol = semi_deviation(conn, ticker, annualize=False)

    if total_vol is None or total_vol == 0 or semi_vol is None:
        return None
    return float(semi_vol / total_vol)


# --------------------------------------------------------------------------- #
# Phase 2 — Risk-Adjusted Return Metrics
# --------------------------------------------------------------------------- #

def sharpe_ratio(
    conn: psycopg.Connection,
    ticker: str,
    risk_free_rate: float | None = None,
) -> float | None:
    """Compute Sharpe ratio using periodic excess returns.

    Methodology:
        1. Compute daily returns
        2. Compute daily risk-free rate: rf_daily = (1 + rf_annual)^(1/252) - 1
        3. Excess return = return - rf_daily
        4. Sharpe = mean(excess) / std(excess, ddof=1) * sqrt(252)

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        risk_free_rate: Annual risk-free rate. Default if None.

    Returns:
        Sharpe ratio as a float, or None.
    """
    rf = risk_free_rate if risk_free_rate is not None else DEFAULT_RISK_FREE_RATE
    rf_daily = (1 + rf) ** (1 / TRADING_DAYS_PER_YEAR) - 1

    returns = daily_returns(conn, ticker)
    if returns is None or returns.empty or len(returns) < 2:
        return None

    excess = returns - rf_daily
    std = excess.std(ddof=1)
    if std == 0:
        return None
    return float(excess.mean() / std * np.sqrt(TRADING_DAYS_PER_YEAR))


def sortino_ratio(
    conn: psycopg.Connection,
    ticker: str,
    risk_free_rate: float | None = None,
    target: float = 0.0,
) -> float | None:
    """Compute Sortino ratio using periodic excess returns.

    Methodology:
        1. Compute daily returns
        2. Compute daily risk-free rate
        3. Excess return = return - rf_daily
        4. Downside deviation = std(min(excess - target_daily, 0), ddof=1) * sqrt(252)
        5. Sortino = mean(excess) / downside_deviation * sqrt(252)

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        risk_free_rate: Annual risk-free rate. Default if None.
        target: Minimum acceptable return (annual, default 0%).

    Returns:
        Sortino ratio as a float, or None.
    """
    rf = risk_free_rate if risk_free_rate is not None else DEFAULT_RISK_FREE_RATE
    rf_daily = (1 + rf) ** (1 / TRADING_DAYS_PER_YEAR) - 1
    target_daily = (1 + target) ** (1 / TRADING_DAYS_PER_YEAR) - 1

    returns = daily_returns(conn, ticker)
    if returns is None or returns.empty or len(returns) < 2:
        return None

    excess = returns - rf_daily
    downside_diff = excess - target_daily
    downside = downside_diff[downside_diff < 0]

    if len(downside) < 2:
        return None

    downside_dev = downside.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)
    if downside_dev == 0:
        return None

    ann_excess = excess.mean() * TRADING_DAYS_PER_YEAR
    return float(ann_excess / downside_dev)


def calmar_ratio(conn: psycopg.Connection, ticker: str) -> float | None:
    """Compute Calmar ratio — annualized return / |max drawdown|.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.

    Returns:
        Calmar ratio as a float, or None.
    """
    dd = max_drawdown(conn, ticker)
    if dd is None or dd == 0:
        return None

    returns = daily_returns(conn, ticker)
    ann_ret = _annualized_return_from_returns(returns)
    if ann_ret is None:
        return None
    return float(ann_ret / abs(dd))


def treynor_ratio(
    conn: psycopg.Connection,
    ticker: str,
    benchmark: str = "SPY",
    risk_free_rate: float | None = None,
) -> float | None:
    """Compute Treynor ratio — excess return per unit of market risk (beta).

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        benchmark: Benchmark ticker for beta calculation.
        risk_free_rate: Annual risk-free rate. Default if None.

    Returns:
        Treynor ratio as a float, or None.
    """
    rf = risk_free_rate if risk_free_rate is not None else DEFAULT_RISK_FREE_RATE
    b = beta(conn, ticker, benchmark)
    if b is None or b == 0:
        return None

    returns = daily_returns(conn, ticker)
    ann_ret = _annualized_return_from_returns(returns)
    if ann_ret is None:
        return None
    return float((ann_ret - rf) / b)


def information_ratio(
    conn: psycopg.Connection,
    ticker: str,
    benchmark: str = "SPY",
) -> float | None:
    """Compute information ratio — active return per unit of tracking error.

    Both active return and tracking error use the same aligned period.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        benchmark: Benchmark ticker.

    Returns:
        Information ratio as a float, or None.
    """
    te = tracking_error(conn, ticker, benchmark)
    if te is None or te == 0:
        return None

    # Use aligned returns for both
    stock_ret = daily_returns(conn, ticker)
    bench_ret = daily_returns(conn, benchmark)
    if stock_ret is None or bench_ret is None:
        return None

    aligned = pd.concat([stock_ret, bench_ret], axis=1).dropna()
    if len(aligned) < 2:
        return None

    ann_stock = _annualized_return_from_returns(aligned.iloc[:, 0])
    ann_bench = _annualized_return_from_returns(aligned.iloc[:, 1])
    if ann_stock is None or ann_bench is None:
        return None

    return float((ann_stock - ann_bench) / te)


def omega_ratio(
    conn: psycopg.Connection,
    ticker: str,
    threshold: float = 0.0,
) -> float | None:
    """Compute Omega ratio — probability-weighted gain/loss ratio.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        threshold: Daily return threshold (default 0).

    Returns:
        Omega ratio, or None if insufficient data.
    """
    returns = daily_returns(conn, ticker)
    if returns is None or returns.empty:
        return None

    gains = returns[returns > threshold] - threshold
    losses = threshold - returns[returns <= threshold]

    if losses.sum() == 0:
        if gains.empty:
            return None
        return float("inf")
    return float(gains.sum() / losses.sum())


def beta(
    conn: psycopg.Connection,
    ticker: str,
    benchmark: str = "SPY",
) -> float | None:
    """Compute beta — sensitivity to benchmark movements.

    Uses OLS regression of aligned daily returns.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        benchmark: Benchmark ticker.

    Returns:
        Beta as a float, or None.
    """
    stock_returns = daily_returns(conn, ticker)
    bench_returns = daily_returns(conn, benchmark)
    if stock_returns is None or bench_returns is None:
        return None

    aligned = pd.concat([stock_returns, bench_returns], axis=1).dropna()
    if len(aligned) < 10:
        return None

    cov = aligned.iloc[:, 0].cov(aligned.iloc[:, 1])
    var = aligned.iloc[:, 1].var()
    if var == 0:
        return None
    return float(cov / var)


def tracking_error(
    conn: psycopg.Connection,
    ticker: str,
    benchmark: str = "SPY",
) -> float | None:
    """Compute tracking error — std dev of excess returns.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        benchmark: Benchmark ticker.

    Returns:
        Annualized tracking error, or None.
    """
    stock_returns = daily_returns(conn, ticker)
    bench_returns = daily_returns(conn, benchmark)
    if stock_returns is None or bench_returns is None:
        return None

    aligned = pd.concat([stock_returns, bench_returns], axis=1).dropna()
    if len(aligned) < 2:
        return None

    excess = aligned.iloc[:, 0] - aligned.iloc[:, 1]
    return float(excess.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))


def alpha(
    conn: psycopg.Connection,
    ticker: str,
    benchmark: str = "SPY",
    risk_free_rate: float | None = None,
) -> float | None:
    """Compute Jensen's alpha — excess return beyond market compensation.

    Uses regression-based alpha (intercept of CAPM regression).

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        benchmark: Benchmark ticker.
        risk_free_rate: Annual risk-free rate. Default if None.

    Returns:
        Alpha as a decimal, or None.
    """
    rf = risk_free_rate if risk_free_rate is not None else DEFAULT_RISK_FREE_RATE
    rf_daily = (1 + rf) ** (1 / TRADING_DAYS_PER_YEAR) - 1

    stock_returns = daily_returns(conn, ticker)
    bench_returns = daily_returns(conn, benchmark)
    if stock_returns is None or bench_returns is None:
        return None

    aligned = pd.concat([stock_returns - rf_daily, bench_returns - rf_daily], axis=1).dropna()
    if len(aligned) < 10:
        return None

    from scipy import stats
    slope, intercept, _, _, _ = stats.linregress(aligned.iloc[:, 1], aligned.iloc[:, 0])

    # Annualize regression alpha
    ann_alpha = intercept * TRADING_DAYS_PER_YEAR
    return float(ann_alpha)


def r_squared(
    conn: psycopg.Connection,
    ticker: str,
    benchmark: str = "SPY",
) -> float | None:
    """Compute R-squared — proportion of variance explained by benchmark.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        benchmark: Benchmark ticker.

    Returns:
        R-squared between 0 and 1, or None.
    """
    stock_returns = daily_returns(conn, ticker)
    bench_returns = daily_returns(conn, benchmark)
    if stock_returns is None or bench_returns is None:
        return None

    aligned = pd.concat([stock_returns, bench_returns], axis=1).dropna()
    if len(aligned) < 2:
        return None

    corr = aligned.iloc[:, 0].corr(aligned.iloc[:, 1])
    return float(corr ** 2)


def single_asset_risk(conn: psycopg.Connection, ticker: str) -> dict:
    """Compute all single-asset risk metrics for a ticker.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.

    Returns:
        Dict with all risk and risk-adjusted metrics.
    """
    return {
        "ticker": ticker,
        # Phase 1 — Risk
        "realized_volatility": realized_volatility(conn, ticker),
        "historical_var_95": historical_var(conn, ticker, confidence=0.95),
        "parametric_var_95": parametric_var(conn, ticker, confidence=0.95),
        "cvar_95": cvar(conn, ticker, confidence=0.95),
        "parkinson_volatility": parkinson_volatility(conn, ticker),
        "garman_klass_volatility": garman_klass_volatility(conn, ticker),
        "max_drawdown": max_drawdown(conn, ticker),
        "semi_deviation": semi_deviation(conn, ticker),
        "downside_ratio": downside_ratio(conn, ticker),
        # Phase 2 — Risk-Adjusted Return
        "sharpe_ratio": sharpe_ratio(conn, ticker),
        "sortino_ratio": sortino_ratio(conn, ticker),
        "calmar_ratio": calmar_ratio(conn, ticker),
        "treynor_ratio": treynor_ratio(conn, ticker),
        "information_ratio": information_ratio(conn, ticker),
        "omega_ratio": omega_ratio(conn, ticker),
        # Phase 3 — Market Risk
        "beta": beta(conn, ticker),
        "alpha": alpha(conn, ticker),
        "r_squared": r_squared(conn, ticker),
        "tracking_error": tracking_error(conn, ticker),
    }


# --------------------------------------------------------------------------- #
# Persist / Load
# --------------------------------------------------------------------------- #

def save_risk_metrics(conn: psycopg.Connection, ticker: str) -> dict:
    """Compute and persist risk metrics for a ticker."""
    ensure_calc_schema(conn)
    metrics = single_asset_risk(conn, ticker)
    metrics["calc_time"] = datetime.now()
    insert_risk_metrics(conn, metrics)
    logger.info("Saved risk metrics for %s at %s", ticker, metrics["calc_time"])
    return metrics


def load_latest_risk_metrics(conn: psycopg.Connection, ticker: str) -> dict | None:
    """Load the most recent persisted risk metrics for a ticker."""
    return get_latest_risk_metrics(conn, ticker)


# --------------------------------------------------------------------------- #
# Phase 4 — Portfolio Risk Metrics
# --------------------------------------------------------------------------- #

def _get_portfolio_weights(conn: psycopg.Connection, portfolio_id: int) -> dict[str, float]:
    """Get portfolio weights as {ticker: weight}.

    Uses cost-basis (units × buy_price) for weight computation.
    """
    securities = get_portfolio_securities(conn, portfolio_id)
    total = sum(s["units"] * s["buy_price"] for s in securities)
    if total == 0:
        return {}
    return {s["ticker"]: (s["units"] * s["buy_price"]) / total for s in securities}


def _get_aligned_portfolio_returns(
    conn: psycopg.Connection,
    portfolio_id: int,
    weights: dict[str, float],
) -> tuple[pd.Series, dict[str, float]] | None:
    """Build aligned portfolio return series with matching weights.

    Returns (portfolio_returns, aligned_weights) where aligned_weights
    contains only tickers with available data, renormalized to sum to 1.

    Returns None if insufficient data.
    """
    available_tickers = []
    for ticker in weights:
        ret = daily_returns(conn, ticker, return_type="adj")
        if ret is not None and not ret.empty:
            available_tickers.append(ticker)

    if not available_tickers:
        return None

    # Build aligned return matrix
    dfs = {}
    for ticker in available_tickers:
        ret = daily_returns(conn, ticker, return_type="adj")
        if ret is not None:
            dfs[ticker] = ret

    if not dfs:
        return None

    returns_df = pd.DataFrame(dfs)
    if returns_df.empty:
        return None

    returns_df = returns_df.dropna(axis=0, how="any")
    if returns_df.empty:
        return None

    # Renormalize weights for available tickers
    available_total = sum(weights[t] for t in available_tickers)
    if available_total == 0:
        return None

    aligned_weights = {t: weights[t] / available_total for t in available_tickers}
    w = np.array([aligned_weights[t] for t in returns_df.columns])

    port_returns = pd.Series(
        np.dot(returns_df.values, w),
        index=returns_df.index,
        name="portfolio_return",
    )
    return port_returns, aligned_weights


def portfolio_beta(conn: psycopg.Connection, portfolio_id: int) -> float | None:
    """Portfolio beta: weighted sum of individual betas.

    Only includes tickers for which beta can be calculated.
    Weights are renormalized for available tickers.

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.

    Returns:
        Portfolio beta, or None if insufficient data.
    """
    from shared.calculations import beta as single_beta

    weights = _get_portfolio_weights(conn, portfolio_id)
    if not weights:
        return None

    betas = []
    for ticker, weight in weights.items():
        b = single_beta(conn, ticker)
        if b is not None:
            betas.append((weight, b))

    if not betas:
        return None

    # Renormalize weights for available betas
    total_w = sum(w for w, _ in betas)
    if total_w == 0:
        return None

    return sum((w / total_w) * b for w, b in betas)


def portfolio_volatility(conn: psycopg.Connection, portfolio_id: int) -> float | None:
    """Portfolio volatility: sqrt(w' × Covariance × w).

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.

    Returns:
        Annualized portfolio volatility (decimal), or None.
    """
    weights = _get_portfolio_weights(conn, portfolio_id)
    if not weights:
        return None

    result = _get_aligned_portfolio_returns(conn, portfolio_id, weights)
    if result is None:
        return None

    port_returns, _ = result
    if len(port_returns) < 30:
        return None

    return float(port_returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))


def portfolio_var(
    conn: psycopg.Connection,
    portfolio_id: int,
    confidence: float = 0.95,
) -> float | None:
    """Portfolio Value at Risk (historical simulation).

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.
        confidence: Confidence level in (0, 1).

    Returns:
        Portfolio VaR (negative = loss), or None.
    """
    _validate_confidence(confidence)

    weights = _get_portfolio_weights(conn, portfolio_id)
    result = _get_aligned_portfolio_returns(conn, portfolio_id, weights)
    if result is None:
        return None

    port_returns, _ = result
    if len(port_returns) < 10:
        return None

    alpha = 1 - confidence
    return float(np.percentile(port_returns, alpha * 100))


def portfolio_cvar(
    conn: psycopg.Connection,
    portfolio_id: int,
    confidence: float = 0.95,
) -> float | None:
    """Portfolio Conditional VaR (Expected Shortfall).

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.
        confidence: Confidence level in (0, 1).

    Returns:
        Portfolio CVaR, or None.
    """
    _validate_confidence(confidence)

    weights = _get_portfolio_weights(conn, portfolio_id)
    result = _get_aligned_portfolio_returns(conn, portfolio_id, weights)
    if result is None:
        return None

    port_returns, _ = result
    if len(port_returns) < 10:
        return None

    var_threshold = float(np.percentile(port_returns, (1 - confidence) * 100))
    tail = port_returns[port_returns <= var_threshold]
    if tail.empty:
        return var_threshold
    return float(tail.mean())


def diversification_ratio(conn: psycopg.Connection, portfolio_id: int) -> float | None:
    """Diversification ratio: (sum of w_i × sigma_i) / sigma_portfolio.

    DR > 1 indicates diversification benefit.

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.

    Returns:
        Diversification ratio, or None.
    """
    weights = _get_portfolio_weights(conn, portfolio_id)
    if not weights:
        return None

    port_vol = portfolio_volatility(conn, portfolio_id)
    if port_vol is None or port_vol == 0:
        return None

    weighted_vols = []
    for ticker, weight in weights.items():
        vol = realized_volatility(conn, ticker)
        if vol is not None:
            weighted_vols.append(weight * vol)

    if not weighted_vols:
        return None

    return sum(weighted_vols) / port_vol


def concentration_index(conn: psycopg.Connection, portfolio_id: int) -> float:
    """Herfindahl-Hirschman index of portfolio weights.

    Range: 1/n (equal weight) to 1 (single holding).

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.

    Returns:
        Concentration index (0-1).
    """
    weights = _get_portfolio_weights(conn, portfolio_id)
    if not weights:
        return 0.0

    return sum(w ** 2 for w in weights.values())


def value_contribution(conn: psycopg.Connection, portfolio_id: int) -> list[dict]:
    """Per-holding contribution to excess return: weight × (return - Rf).

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.

    Returns:
        List of dicts sorted by contribution descending.
    """
    weights = _get_portfolio_weights(conn, portfolio_id)
    if not weights:
        return []

    results = []
    for ticker, weight in weights.items():
        returns = daily_returns(conn, ticker, return_type="adj")
        if returns is None or returns.empty:
            continue

        ann_ret = _annualized_return_from_returns(returns)
        if ann_ret is None:
            continue

        excess = ann_ret - DEFAULT_RISK_FREE_RATE
        results.append({
            "ticker": ticker,
            "weight": weight,
            "annual_return": ann_ret,
            "contribution": weight * excess,
        })

    return sorted(results, key=lambda x: x["contribution"], reverse=True)


def portfolio_risk(conn: psycopg.Connection, portfolio_id: int) -> dict:
    """Compute all portfolio-level risk metrics."""
    return {
        "portfolio_id": portfolio_id,
        "portfolio_beta": portfolio_beta(conn, portfolio_id),
        "portfolio_volatility": portfolio_volatility(conn, portfolio_id),
        "portfolio_var_95": portfolio_var(conn, portfolio_id, confidence=0.95),
        "portfolio_cvar_95": portfolio_cvar(conn, portfolio_id, confidence=0.95),
        "diversification_ratio": diversification_ratio(conn, portfolio_id),
        "concentration_index": concentration_index(conn, portfolio_id),
        "value_contributions": value_contribution(conn, portfolio_id),
    }


# --------------------------------------------------------------------------- #
# Persist / Load (Portfolio Risk)
# --------------------------------------------------------------------------- #

def save_portfolio_risk(conn: psycopg.Connection, portfolio_id: int) -> dict:
    """Compute and persist portfolio risk metrics."""
    ensure_calc_schema(conn)
    risk = portfolio_risk(conn, portfolio_id)
    risk["calc_time"] = datetime.now()
    save_data = {k: v for k, v in risk.items() if k != "value_contributions"}
    insert_portfolio_risk(conn, save_data)
    logger.info("Saved portfolio risk for portfolio %d at %s", portfolio_id, risk["calc_time"])
    return risk


def load_latest_portfolio_risk(conn: psycopg.Connection, portfolio_id: int) -> dict | None:
    """Load the most recent persisted portfolio risk metrics."""
    return get_latest_portfolio_risk(conn, portfolio_id)


# --------------------------------------------------------------------------- #
# Phase 5 — Scenario Analysis
# --------------------------------------------------------------------------- #

CRISIS_PERIODS = {
    "COVID Crash (2020)": ("2020-02-19", "2020-03-23"),
    "2008 Financial Crisis": ("2007-10-09", "2009-03-09"),
    "Dot-com Bubble (2000)": ("2000-03-10", "2002-10-09"),
    "2022 Bear Market": ("2022-01-03", "2022-10-12"),
}


def historical_stress_test(conn: psycopg.Connection, ticker: str) -> list[dict]:
    """Apply historical crisis returns to current ticker.

    Uses actual peak-to-trough analysis within each crisis window,
    not just first-to-last observation.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.

    Returns:
        List of dicts with crisis name, peak-to-trough loss, and projected impact.
    """
    df = get_candles_df(conn, ticker)
    if df is None or df.empty:
        return []

    results = []
    for crisis_name, (start_date, end_date) in CRISIS_PERIODS.items():
        # Get data within crisis window
        mask = (df.index >= start_date) & (df.index <= end_date)
        crisis_df = df[mask]
        if crisis_df.empty or len(crisis_df) < 2:
            continue

        prices = crisis_df.get("adj_close", crisis_df["close"])

        # Find actual peak-to-trough within the window
        cummax = prices.cummax()
        drawdown = (prices - cummax) / cummax
        trough_idx = drawdown.idxmin()
        peak_value = cummax.loc[trough_idx]
        trough_value = prices.loc[trough_idx]
        peak_to_trough_return = float(trough_value / peak_value - 1)

        # Apply to current price
        current_price = float(prices.iloc[-1])
        projected_price = current_price * (1 + peak_to_trough_return)

        results.append({
            "crisis": crisis_name,
            "crisis_return": peak_to_trough_return,
            "current_price": current_price,
            "projected_price": projected_price,
            "projected_loss": current_price - projected_price,
            "peak_date": str(cummax.loc[:trough_idx].idxmax()),
            "trough_date": str(trough_idx),
        })

    return sorted(results, key=lambda x: x["crisis_return"])


def drawdown_duration(conn: psycopg.Connection, ticker: str) -> dict:
    """Compute drawdown duration and recovery time.

    Separates:
    - time_to_trough: days from peak to trough
    - recovery_time: days from trough to recovery
    - total_duration: days from peak to recovery

    Args:
        conn: Database connection.
        ticker: Ticker symbol.

    Returns:
        Dict with drawdown metrics.
    """
    df = get_candles_df(conn, ticker)
    if df is None or df.empty:
        return {
            "max_drawdown_duration": 0,
            "current_drawdown_duration": 0,
            "max_recovery_time": 0,
            "drawdown_events": 0,
        }

    prices = df.get("adj_close", df["close"])
    peak = prices.expanding().max()
    drawdown = (prices - peak) / peak

    in_drawdown = drawdown < 0
    drawdown_starts = in_drawdown & (~in_drawdown).shift(1).fillna(True)
    drawdown_ends = (~in_drawdown) & in_drawdown.shift(1).fillna(False)

    durations = []
    recovery_times = []
    trough_durations = []
    start_idx = None

    for i, (start, end) in enumerate(zip(drawdown_starts, drawdown_ends)):
        if start:
            start_idx = i
        if end and start_idx is not None:
            # Find trough within this drawdown period
            dd_slice = drawdown.iloc[start_idx:i]
            trough_offset = dd_slice.argmin()
            trough_idx_local = start_idx + trough_offset

            time_to_trough = trough_idx_local - start_idx
            recovery_time = i - trough_idx_local
            total_duration = i - start_idx

            trough_durations.append(time_to_trough)
            recovery_times.append(recovery_time)
            durations.append(total_duration)
            start_idx = None

    # Current drawdown if still in one
    if start_idx is not None:
        current_duration = len(prices) - start_idx
    else:
        current_duration = 0

    return {
        "max_drawdown_duration": max(durations) if durations else 0,
        "current_drawdown_duration": current_duration,
        "max_recovery_time": max(recovery_times) if recovery_times else 0,
        "drawdown_events": len(durations),
    }


def win_rate(conn: psycopg.Connection, ticker: str, period: str = "monthly") -> dict:
    """Compute win rate (% of positive return periods).

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        period: 'daily', 'weekly', or 'monthly'.

    Returns:
        Dict with win_rate, total_periods, winning_periods, losing_periods.
    """
    _validate_period(period)

    df = get_candles_df(conn, ticker)
    if df is None or df.empty:
        return {"win_rate": 0, "total_periods": 0, "winning_periods": 0, "losing_periods": 0}

    prices = df.get("adj_close", df["close"])

    if period == "daily":
        returns = prices.pct_change().dropna()
    elif period == "weekly":
        weekly = prices.resample("W").last().dropna()
        returns = weekly.pct_change().dropna()
    else:  # monthly
        monthly = prices.resample("ME").last().dropna()
        returns = monthly.pct_change().dropna()

    total = len(returns)
    if total == 0:
        return {"win_rate": 0, "total_periods": 0, "winning_periods": 0, "losing_periods": 0}

    winning = int((returns > 0).sum())
    losing = int((returns < 0).sum())

    return {
        "win_rate": winning / total,
        "total_periods": total,
        "winning_periods": winning,
        "losing_periods": losing,
    }


def profit_factor(conn: psycopg.Connection, ticker: str) -> float | None:
    """Compute profit factor: gross gains / gross losses.

    Returns None if no losses (not infinite).
    """
    df = get_candles_df(conn, ticker)
    if df is None or df.empty:
        return None

    prices = df.get("adj_close", df["close"])
    returns = prices.pct_change().dropna()
    gains = returns[returns > 0].sum()
    losses = abs(returns[returns < 0].sum())

    if losses == 0:
        return None
    return float(gains / losses)


def scenario_analysis(conn: psycopg.Connection, ticker: str) -> dict:
    """Compute all scenario analysis metrics for a ticker."""
    return {
        "ticker": ticker,
        "stress_test": historical_stress_test(conn, ticker),
        "drawdown": drawdown_duration(conn, ticker),
        "win_rate": win_rate(conn, ticker),
        "profit_factor": profit_factor(conn, ticker),
    }
