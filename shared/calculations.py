"""Portfolio exposure and risk calculations.

Computes sector/industry exposure and single-asset risk metrics.
All functions accept a psycopg Connection — no global state.
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
RISK_FREE_RATE = 0.05  # 5% annual — override via config or pass as param


def portfolio_sector_exposure(conn: psycopg.Connection, portfolio_id: int) -> list[dict]:
    """Compute sector exposure for a portfolio.

    Groups securities by sector and sums their market values,
    then converts to weights.

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.

    Returns:
        List of dicts sorted by weight descending:
        [{"sector": "Technology", "weight": 0.45, "tickers": ["AAPL", "MSFT"]}, ...]

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

    Groups securities by industry and sums their market values,
    then converts to weights.

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.

    Returns:
        List of dicts sorted by weight descending:
        [{"industry": "Semiconductors", "weight": 0.30, "tickers": ["NVDA"]}, ...]

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
        Dict with "sector" and "industry" keys, each holding a list of exposure dicts.
    """
    return {
        "sector": portfolio_sector_exposure(conn, portfolio_id),
        "industry": portfolio_industry_exposure(conn, portfolio_id),
    }


# --------------------------------------------------------------------------- #
# Phase 1 — Single-Asset Risk Metrics
# --------------------------------------------------------------------------- #

def daily_returns(
    conn: psycopg.Connection,
    ticker: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.Series:
    """Compute daily simple returns from close prices.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        start_date: Optional start date filter.
        end_date: Optional end date filter.

    Returns:
        Series of daily returns indexed by trade_date.
    """
    df = get_candles_df(conn, ticker, start_date, end_date)
    if df.empty or len(df) < 2:
        return pd.Series(dtype=float)
    return df["close"].pct_change().dropna()


def realized_volatility(
    conn: psycopg.Connection,
    ticker: str,
    window: int | None = None,
    annualize: bool = True,
) -> float:
    """Compute realized volatility (standard deviation of returns).

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        window: If None, use all data. If int, use last N periods.
        annualize: If True, multiply by sqrt(252).

    Returns:
        Volatility as a float.
    """
    returns = daily_returns(conn, ticker)
    if returns.empty:
        return 0.0

    if window is not None:
        returns = returns.tail(window)

    vol = returns.std()
    if annualize:
        vol *= np.sqrt(TRADING_DAYS_PER_YEAR)
    return float(vol)


def historical_var(
    conn: psycopg.Connection,
    ticker: str,
    confidence: float = 0.95,
    horizon: int = 1,
) -> float:
    """Compute Historical Value at Risk.

    Uses empirical percentile of historical returns.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        confidence: Confidence level (e.g. 0.95 for 95%).
        horizon: Number of days for VaR projection.

    Returns:
        VaR as a negative number (e.g. -0.03 means 3% max loss).
    """
    returns = daily_returns(conn, ticker)
    if returns.empty:
        return 0.0

    # Scale for horizon
    if horizon > 1:
        returns = returns / np.sqrt(horizon)  # Scale to 1-day equivalent

    percentile = (1 - confidence) * 100
    var = np.percentile(returns, percentile)
    return float(var)


def parametric_var(
    conn: psycopg.Connection,
    ticker: str,
    confidence: float = 0.95,
    horizon: int = 1,
) -> float:
    """Compute Parametric VaR (variance-covariance method).

    Assumes normal distribution of returns.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        confidence: Confidence level (e.g. 0.95 for 95%).
        horizon: Number of days for VaR projection.

    Returns:
        VaR as a negative number.
    """
    returns = daily_returns(conn, ticker)
    if returns.empty:
        return 0.0

    from scipy import stats

    mean = returns.mean()
    std = returns.std()

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
) -> float:
    """Compute Conditional VaR (Expected Shortfall).

    Mean of all returns that are worse than VaR.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        confidence: Confidence level (e.g. 0.95 for 95%).

    Returns:
        CVaR as a negative number (always worse than VaR).
    """
    returns = daily_returns(conn, ticker)
    if returns.empty:
        return 0.0

    var_threshold = historical_var(conn, ticker, confidence)
    tail_returns = returns[returns <= var_threshold]

    if tail_returns.empty:
        return var_threshold
    return float(tail_returns.mean())


def parkinson_volatility(
    conn: psycopg.Connection,
    ticker: str,
    annualize: bool = True,
) -> float:
    """Compute Parkinson volatility using high/low price range.

    More accurate than close-only volatility.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        annualize: If True, multiply by sqrt(252).

    Returns:
        Parkinson volatility as a float.
    """
    df = get_candles_df(conn, ticker)
    if df.empty or len(df) < 2:
        return 0.0

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
) -> float:
    """Compute Garman-Klass volatility using OHLC data.

    Most efficient OHLC-based volatility estimator.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        annualize: If True, multiply by sqrt(252).

    Returns:
        Garman-Klass volatility as a float.
    """
    df = get_candles_df(conn, ticker)
    if df.empty or len(df) < 2:
        return 0.0

    log_hl = np.log(df["high"] / df["low"])
    log_co = np.log(df["close"] / df["open"])

    gk_var = 0.5 * (log_hl ** 2).sum() - (2 * np.log(2) - 1) * (log_co ** 2).sum()
    gk_var /= len(df)
    vol = np.sqrt(max(gk_var, 0))

    if annualize:
        vol *= np.sqrt(TRADING_DAYS_PER_YEAR)
    return float(vol)


def max_drawdown(conn: psycopg.Connection, ticker: str) -> float:
    """Compute maximum drawdown from peak.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.

    Returns:
        Maximum drawdown as a negative number (e.g. -0.35 for 35% drawdown).
    """
    df = get_candles_df(conn, ticker)
    if df.empty or len(df) < 2:
        return 0.0

    cummax = df["close"].cummax()
    drawdown = (df["close"] - cummax) / cummax
    return float(drawdown.min())


def semi_deviation(
    conn: psycopg.Connection,
    ticker: str,
    annualize: bool = True,
) -> float:
    """Compute semi-deviation (downside volatility).

    Only considers negative returns.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        annualize: If True, multiply by sqrt(252).

    Returns:
        Semi-deviation as a float.
    """
    returns = daily_returns(conn, ticker)
    if returns.empty:
        return 0.0

    negative_returns = returns[returns < 0]
    if negative_returns.empty:
        return 0.0

    semi_var = (negative_returns ** 2).sum() / len(returns)
    semi_vol = np.sqrt(semi_var)

    if annualize:
        semi_vol *= np.sqrt(TRADING_DAYS_PER_YEAR)
    return float(semi_vol)


def downside_ratio(conn: psycopg.Connection, ticker: str) -> float:
    """Compute downside ratio (semi-deviation / total volatility).

    Proportion of total risk that is downside.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.

    Returns:
        Ratio between 0 and 1. Higher = more downside risk.
    """
    total_vol = realized_volatility(conn, ticker, annualize=False)
    semi_vol = semi_deviation(conn, ticker, annualize=False)

    if total_vol == 0:
        return 0.0
    return float(semi_vol / total_vol)


# --------------------------------------------------------------------------- #
# Phase 2 — Risk-Adjusted Return Metrics
# --------------------------------------------------------------------------- #

def _annualized_return(conn: psycopg.Connection, ticker: str) -> float:
    """Compute annualized return from daily close prices."""
    df = get_candles_df(conn, ticker)
    if df.empty or len(df) < 2:
        return 0.0
    total_return = df["close"].iloc[-1] / df["close"].iloc[0]
    years = len(df) / TRADING_DAYS_PER_YEAR
    if years <= 0 or total_return <= 0:
        return 0.0
    return float(total_return ** (1 / years) - 1)


def sharpe_ratio(
    conn: psycopg.Connection,
    ticker: str,
    risk_free_rate: float | None = None,
) -> float:
    """Compute Sharpe ratio — excess return per unit of total risk.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        risk_free_rate: Annual risk-free rate. Uses default if None.

    Returns:
        Sharpe ratio as a float.
    """
    rf = risk_free_rate if risk_free_rate is not None else RISK_FREE_RATE
    vol = realized_volatility(conn, ticker)
    if vol == 0:
        return 0.0
    ann_ret = _annualized_return(conn, ticker)
    return float((ann_ret - rf) / vol)


def sortino_ratio(
    conn: psycopg.Connection,
    ticker: str,
    risk_free_rate: float | None = None,
) -> float:
    """Compute Sortino ratio — excess return per unit of downside risk.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        risk_free_rate: Annual risk-free rate. Uses default if None.

    Returns:
        Sortino ratio as a float.
    """
    rf = risk_free_rate if risk_free_rate is not None else RISK_FREE_RATE
    semi = semi_deviation(conn, ticker)
    if semi == 0:
        return 0.0
    ann_ret = _annualized_return(conn, ticker)
    return float((ann_ret - rf) / semi)


def calmar_ratio(conn: psycopg.Connection, ticker: str) -> float:
    """Compute Calmar ratio — annualized return per unit of max drawdown.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.

    Returns:
        Calmar ratio as a float.
    """
    dd = max_drawdown(conn, ticker)
    if dd == 0:
        return 0.0
    ann_ret = _annualized_return(conn, ticker)
    return float(ann_ret / abs(dd))


def treynor_ratio(
    conn: psycopg.Connection,
    ticker: str,
    benchmark: str = "SPY",
    risk_free_rate: float | None = None,
) -> float:
    """Compute Treynor ratio — excess return per unit of market risk (beta).

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        benchmark: Benchmark ticker for beta calculation.
        risk_free_rate: Annual risk-free rate. Uses default if None.

    Returns:
        Treynor ratio as a float.
    """
    rf = risk_free_rate if risk_free_rate is not None else RISK_FREE_RATE
    b = beta(conn, ticker, benchmark)
    if b == 0:
        return 0.0
    ann_ret = _annualized_return(conn, ticker)
    return float((ann_ret - rf) / b)


def information_ratio(
    conn: psycopg.Connection,
    ticker: str,
    benchmark: str = "SPY",
) -> float:
    """Compute information ratio — active return per unit of tracking error.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        benchmark: Benchmark ticker.

    Returns:
        Information ratio as a float.
    """
    te = tracking_error(conn, ticker, benchmark)
    if te == 0:
        return 0.0
    active_return = _annualized_return(conn, ticker) - _annualized_return(conn, benchmark)
    return float(active_return / te)


def omega_ratio(
    conn: psycopg.Connection,
    ticker: str,
    threshold: float = 0.0,
) -> float:
    """Compute Omega ratio — probability-weighted gain/loss ratio.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        threshold: Return threshold (default 0 = risk-free).

    Returns:
        Omega ratio. >1 means more upside than downside.
    """
    returns = daily_returns(conn, ticker)
    if returns.empty:
        return 0.0

    gains = returns[returns > threshold] - threshold
    losses = threshold - returns[returns <= threshold]

    if losses.sum() == 0:
        return float("inf") if not gains.empty else 0.0
    return float(gains.sum() / losses.sum())


def beta(
    conn: psycopg.Connection,
    ticker: str,
    benchmark: str = "SPY",
) -> float:
    """Compute beta — sensitivity to benchmark movements.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        benchmark: Benchmark ticker.

    Returns:
        Beta as a float.
    """
    stock_returns = daily_returns(conn, ticker)
    bench_returns = daily_returns(conn, benchmark)
    if stock_returns.empty or bench_returns.empty:
        return 0.0

    aligned = pd.concat([stock_returns, bench_returns], axis=1).dropna()
    if len(aligned) < 2:
        return 0.0

    cov = aligned.iloc[:, 0].cov(aligned.iloc[:, 1])
    var = aligned.iloc[:, 1].var()
    if var == 0:
        return 0.0
    return float(cov / var)


def tracking_error(
    conn: psycopg.Connection,
    ticker: str,
    benchmark: str = "SPY",
) -> float:
    """Compute tracking error — std dev of excess returns.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        benchmark: Benchmark ticker.

    Returns:
        Annualized tracking error.
    """
    stock_returns = daily_returns(conn, ticker)
    bench_returns = daily_returns(conn, benchmark)
    if stock_returns.empty or bench_returns.empty:
        return 0.0

    aligned = pd.concat([stock_returns, bench_returns], axis=1).dropna()
    if len(aligned) < 2:
        return 0.0

    excess = aligned.iloc[:, 0] - aligned.iloc[:, 1]
    return float(excess.std() * np.sqrt(TRADING_DAYS_PER_YEAR))


def alpha(
    conn: psycopg.Connection,
    ticker: str,
    benchmark: str = "SPY",
    risk_free_rate: float | None = None,
) -> float:
    """Compute Jensen's alpha — excess return beyond market compensation.

    Formula: alpha = R_p - (Rf + Beta * (R_m - Rf))

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        benchmark: Benchmark ticker.
        risk_free_rate: Annual risk-free rate. Uses default if None.

    Returns:
        Alpha as a float.
    """
    rf = risk_free_rate if risk_free_rate is not None else RISK_FREE_RATE
    b = beta(conn, ticker, benchmark)
    ann_ret = _annualized_return(conn, ticker)
    bench_ret = _annualized_return(conn, benchmark)
    return float(ann_ret - (rf + b * (bench_ret - rf)))


def r_squared(
    conn: psycopg.Connection,
    ticker: str,
    benchmark: str = "SPY",
) -> float:
    """Compute R-squared — proportion of variance explained by benchmark.

    Formula: correlation(stock, benchmark)^2

    Args:
        conn: Database connection.
        ticker: Ticker symbol.
        benchmark: Benchmark ticker.

    Returns:
        R-squared between 0 and 1.
    """
    stock_returns = daily_returns(conn, ticker)
    bench_returns = daily_returns(conn, benchmark)
    if stock_returns.empty or bench_returns.empty:
        return 0.0

    aligned = pd.concat([stock_returns, bench_returns], axis=1).dropna()
    if len(aligned) < 2:
        return 0.0

    corr = aligned.iloc[:, 0].corr(aligned.iloc[:, 1])
    return float(corr ** 2)


def single_asset_risk(conn: psycopg.Connection, ticker: str) -> dict:
    """Compute all single-asset risk metrics for a ticker.

    Includes Phase 1 (risk), Phase 2 (risk-adjusted return),
    and Phase 3 (market risk) metrics.

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
    """Compute and persist risk metrics for a ticker.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.

    Returns:
        The saved metrics dict with calc_time.
    """
    ensure_calc_schema(conn)

    metrics = single_asset_risk(conn, ticker)
    metrics["calc_time"] = datetime.now()

    insert_risk_metrics(conn, metrics)
    logger.info("Saved risk metrics for %s at %s", ticker, metrics["calc_time"])
    return metrics


def load_latest_risk_metrics(conn: psycopg.Connection, ticker: str) -> dict | None:
    """Load the most recent persisted risk metrics for a ticker.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.

    Returns:
        Dict with risk metrics and calc_time, or None if not found.
    """
    return get_latest_risk_metrics(conn, ticker)


# --------------------------------------------------------------------------- #
# Phase 4 — Portfolio Risk Metrics
# --------------------------------------------------------------------------- #

def _get_portfolio_weights(conn: psycopg.Connection, portfolio_id: int) -> dict[str, float]:
    """Get portfolio weights as {ticker: weight}.

    Weights are computed as (units × buy_price) / total_market_value.
    """
    securities = get_portfolio_securities(conn, portfolio_id)
    total = sum(s["units"] * s["buy_price"] for s in securities)
    if total == 0:
        return {}
    return {s["ticker"]: (s["units"] * s["buy_price"]) / total for s in securities}


def _get_portfolio_returns(conn: psycopg.Connection, portfolio_id: int, weights: dict[str, float]) -> pd.Series:
    """Get weighted portfolio daily returns."""
    tickers = list(weights.keys())
    w = np.array([weights[t] for t in tickers])

    dfs = {}
    for ticker in tickers:
        df = get_candles_df(conn, ticker)
        if df is not None and not df.empty:
            dfs[ticker] = df["adj_close"].pct_change().dropna()

    if not dfs:
        return pd.Series(dtype=float)

    returns_df = pd.DataFrame(dfs).dropna()
    if returns_df.empty:
        return pd.Series(dtype=float)

    return pd.Series(np.dot(returns_df.values, w), index=returns_df.index, name="portfolio_return")


def portfolio_beta(conn: psycopg.Connection, portfolio_id: int) -> float | None:
    """Portfolio beta: weighted sum of individual betas.

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.

    Returns:
        Portfolio beta, or None if SPY data missing.
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

    return sum(w * b for w, b in betas)


def portfolio_volatility(conn: psycopg.Connection, portfolio_id: int) -> float | None:
    """Portfolio volatility: sqrt(w' × Covariance × w).

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.

    Returns:
        Annualized portfolio volatility (decimal), or None if insufficient data.
    """
    weights = _get_portfolio_weights(conn, portfolio_id)
    if not weights:
        return None

    tickers = list(weights.keys())
    w = np.array([weights[t] for t in tickers])

    dfs = {}
    for ticker in tickers:
        df = get_candles_df(conn, ticker)
        if df is not None and not df.empty:
            dfs[ticker] = df["adj_close"].pct_change().dropna()

    if len(dfs) < 2:
        return None

    returns_df = pd.DataFrame(dfs).dropna()
    if returns_df.empty or len(returns_df) < 30:
        return None

    cov_matrix = returns_df.cov().values
    port_var = float(np.dot(w, np.dot(cov_matrix, w)))
    return np.sqrt(port_var * TRADING_DAYS_PER_YEAR)


def portfolio_var(conn: psycopg.Connection, portfolio_id: int,
                  confidence: float = 0.95) -> float | None:
    """Portfolio Value at Risk (historical simulation).

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.
        confidence: Confidence level (default 95%).

    Returns:
        Portfolio VaR (negative number = loss), or None.
    """
    weights = _get_portfolio_weights(conn, portfolio_id)
    port_returns = _get_portfolio_returns(conn, portfolio_id, weights)
    if port_returns.empty:
        return None

    alpha = 1 - confidence
    return float(np.percentile(port_returns, alpha * 100))


def portfolio_cvar(conn: psycopg.Connection, portfolio_id: int,
                   confidence: float = 0.95) -> float | None:
    """Portfolio Conditional VaR (Expected Shortfall).

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.
        confidence: Confidence level (default 95%).

    Returns:
        Portfolio CVaR (mean of losses beyond VaR), or None.
    """
    weights = _get_portfolio_weights(conn, portfolio_id)
    port_returns = _get_portfolio_returns(conn, portfolio_id, weights)
    if port_returns.empty:
        return None

    var = portfolio_var(conn, portfolio_id, confidence)
    if var is None:
        return None

    return float(port_returns[port_returns <= var].mean())


def diversification_ratio(conn: psycopg.Connection, portfolio_id: int) -> float | None:
    """Diversification ratio: (sum of w_i × sigma_i) / sigma_portfolio.

    Values > 1 indicate diversification benefit.

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
            weighted_vols.append(weight * vol / 100)

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
        List of dicts sorted by contribution descending:
        [{"ticker": "AAPL", "weight": 0.3, "contribution": 0.02}, ...]
    """
    weights = _get_portfolio_weights(conn, portfolio_id)
    if not weights:
        return []

    results = []
    for ticker, weight in weights.items():
        df = get_candles_df(conn, ticker)
        if df is None or df.empty:
            continue

        daily_returns = df["adj_close"].pct_change().dropna()
        if daily_returns.empty:
            continue

        annual_return = float(daily_returns.mean() * TRADING_DAYS_PER_YEAR)
        excess = annual_return - RISK_FREE_RATE
        results.append({
            "ticker": ticker,
            "weight": weight,
            "annual_return": annual_return,
            "contribution": weight * excess,
        })

    return sorted(results, key=lambda x: x["contribution"], reverse=True)


def portfolio_risk(conn: psycopg.Connection, portfolio_id: int) -> dict:
    """Compute all portfolio-level risk metrics.

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.

    Returns:
        Dict with all portfolio risk metrics.
    """
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
    """Compute and persist portfolio risk metrics.

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.

    Returns:
        The saved portfolio risk dict with calc_time.
    """
    ensure_calc_schema(conn)

    risk = portfolio_risk(conn, portfolio_id)
    risk["calc_time"] = datetime.now()

    # Remove value_contributions (list, not scalar)
    save_data = {k: v for k, v in risk.items() if k != "value_contributions"}

    insert_portfolio_risk(conn, save_data)
    logger.info("Saved portfolio risk for portfolio %d at %s", portfolio_id, risk["calc_time"])
    return risk


def load_latest_portfolio_risk(conn: psycopg.Connection, portfolio_id: int) -> dict | None:
    """Load the most recent persisted portfolio risk metrics.

    Args:
        conn: Database connection.
        portfolio_id: Portfolio id.

    Returns:
        Dict with portfolio risk metrics and calc_time, or None if not found.
    """
    return get_latest_portfolio_risk(conn, portfolio_id)


# --------------------------------------------------------------------------- #
# Phase 5 — Scenario Analysis
# --------------------------------------------------------------------------- #

# Historical crisis periods (approximate peak-to-trough dates)
CRISIS_PERIODS = {
    "COVID Crash (2020)": ("2020-02-19", "2020-03-23"),
    "2008 Financial Crisis": ("2007-10-09", "2009-03-09"),
    "Dot-com Bubble (2000)": ("2000-03-10", "2002-10-09"),
    "2022 Bear Market": ("2022-01-03", "2022-10-12"),
}


def historical_stress_test(conn: psycopg.Connection, ticker: str) -> list[dict]:
    """Apply historical crisis returns to current ticker.

    Computes what would happen if the current ticker experienced
    the same percentage declines as during past crises.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.

    Returns:
        List of dicts with crisis name, crisis decline, and projected impact.
    """
    df = get_candles_df(conn, ticker)
    if df is None or df.empty:
        return []

    results = []
    for crisis_name, (start_date, end_date) in CRISIS_PERIODS.items():
        crisis_df = df.loc[start_date:end_date]
        if crisis_df.empty or len(crisis_df) < 2:
            continue

        # Calculate crisis return (peak to trough)
        crisis_return = float(crisis_df["adj_close"].iloc[-1] / crisis_df["adj_close"].iloc[0] - 1)

        # Apply to current price
        current_price = float(df["adj_close"].iloc[-1])
        projected_price = current_price * (1 + crisis_return)

        results.append({
            "crisis": crisis_name,
            "crisis_return": crisis_return,
            "current_price": current_price,
            "projected_price": projected_price,
            "projected_loss": current_price - projected_price,
        })

    return sorted(results, key=lambda x: x["crisis_return"])


def drawdown_duration(conn: psycopg.Connection, ticker: str) -> dict:
    """Compute drawdown duration and recovery time.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.

    Returns:
        Dict with max_drawdown_duration, current_drawdown_duration,
        max_recovery_time, and drawdown_events.
    """
    df = get_candles_df(conn, ticker)
    if df is None or df.empty:
        return {"max_drawdown_duration": 0, "current_drawdown_duration": 0,
                "max_recovery_time": 0, "drawdown_events": 0}

    prices = df["adj_close"]
    peak = prices.expanding().max()
    drawdown = (prices - peak) / peak

    # Find drawdown periods
    in_drawdown = drawdown < 0
    drawdown_starts = in_drawdown & ~in_drawdown.shift(1).fillna(False)
    drawdown_ends = ~in_drawdown & in_drawdown.shift(1).fillna(False)

    durations = []
    recovery_times = []
    start_idx = None

    for i, (start, end) in enumerate(zip(drawdown_starts, drawdown_ends)):
        if start:
            start_idx = i
        if end and start_idx is not None:
            duration = i - start_idx
            durations.append(duration)
            # Recovery time is time from trough to peak recovery
            recovery_times.append(duration)
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
    df = get_candles_df(conn, ticker)
    if df is None or df.empty:
        return {"win_rate": 0, "total_periods": 0, "winning_periods": 0, "losing_periods": 0}

    prices = df["adj_close"]

    if period == "daily":
        returns = prices.pct_change().dropna()
    elif period == "weekly":
        weekly = prices.resample("W").last().dropna()
        returns = weekly.pct_change().dropna()
    elif period == "monthly":
        monthly = prices.resample("ME").last().dropna()
        returns = monthly.pct_change().dropna()
    else:
        return {"win_rate": 0, "total_periods": 0, "winning_periods": 0, "losing_periods": 0}

    total = len(returns)
    winning = int((returns > 0).sum())
    losing = int((returns < 0).sum())

    return {
        "win_rate": winning / total if total > 0 else 0,
        "total_periods": total,
        "winning_periods": winning,
        "losing_periods": losing,
    }


def profit_factor(conn: psycopg.Connection, ticker: str) -> float | None:
    """Compute profit factor: gross gains / gross losses.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.

    Returns:
        Profit factor (>1 = profitable), or None if no losses.
    """
    df = get_candles_df(conn, ticker)
    if df is None or df.empty:
        return None

    returns = df["adj_close"].pct_change().dropna()
    gains = returns[returns > 0].sum()
    losses = abs(returns[returns < 0].sum())

    if losses == 0:
        return None

    return float(gains / losses)


def scenario_analysis(conn: psycopg.Connection, ticker: str) -> dict:
    """Compute all scenario analysis metrics for a ticker.

    Args:
        conn: Database connection.
        ticker: Ticker symbol.

    Returns:
        Dict with all scenario analysis metrics.
    """
    return {
        "ticker": ticker,
        "stress_test": historical_stress_test(conn, ticker),
        "drawdown": drawdown_duration(conn, ticker),
        "win_rate": win_rate(conn, ticker),
        "profit_factor": profit_factor(conn, ticker),
    }
