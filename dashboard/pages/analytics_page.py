"""Data Analytics page.

Calculations, performance metrics, correlations, and analytical charts.
All computations use data from shared/ queries and pandas/plotly.
"""
from __future__ import annotations

import logging
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from shared.config import load_db_config
from shared.db import get_connection
from shared.queries import (
    get_all_tickers,
    get_multi_ticker_candles_df,
    get_sync_summary,
    get_tickers_with_stats,
)

logger = logging.getLogger(__name__)

CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$", "EUR": "\u20ac", "GBP": "\u00a3", "JPY": "\u00a5",
    "INR": "\u20b9", "CAD": "C$", "AUD": "A$", "CHF": "CHF ",
    "CNY": "\u00a5", "HKD": "HK$", "SGD": "S$", "KRW": "\u20a9",
}


def _currency_fmt(amount: float, currency: str | None) -> str:
    """Format a monetary amount with the correct currency symbol."""
    symbol = CURRENCY_SYMBOLS.get((currency or "USD").upper(), f"{currency} ")
    return f"{symbol}{amount:,.2f}"


def _calculate_returns(prices: pd.Series) -> pd.Series:
    return prices.pct_change().dropna()


def _calculate_cumulative_returns(returns: pd.Series) -> pd.Series:
    return (1 + returns).cumprod() - 1


def _calculate_max_drawdown(prices: pd.Series) -> float:
    if prices.empty:
        return 0.0
    cummax = prices.cummax()
    drawdown = (prices - cummax) / cummax
    return float(drawdown.min())


def _calculate_cagr(prices: pd.Series) -> float | None:
    if len(prices) < 2:
        return None
    total_return = prices.iloc[-1] / prices.iloc[0]
    days = (prices.index[-1] - prices.index[0]).days
    if days <= 0:
        return None
    years = days / 365.25
    if total_return <= 0 or years <= 0:
        return None
    return float(total_return ** (1 / years) - 1)


st.title("Data Analytics")
st.markdown("Performance analysis, comparisons, and market insights.")

config = load_db_config()

try:
    with get_connection(config) as conn:
        summary = get_sync_summary(conn)
        all_tickers = get_all_tickers(conn)
        tickers_with_stats = get_tickers_with_stats(conn)
except Exception as e:
    st.error(f"Failed to load data: {e}")
    logger.error("Failed to load data: %s", e)
    st.stop()

# Build ticker -> currency map
currency_map: dict[str, str] = {t["ticker"]: t.get("currency") or "USD" for t in all_tickers}

# ------------------------------------------------------------------ #
# Overview metrics
# ------------------------------------------------------------------ #
st.subheader("Database Overview")
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Tickers", summary["total_tickers"])
c2.metric("Candles", f"{summary['total_candles']:,}")
c3.metric("Dividends", f"{summary['total_dividends']:,}")
c4.metric("Splits", f"{summary['total_splits']:,}")
c5.metric("From", str(summary["min_date"]))
c6.metric("To", str(summary["max_date"]))

st.markdown("---")

if not all_tickers:
    st.info("No tickers available for analysis.")
    st.stop()

# ------------------------------------------------------------------ #
# Multi-ticker comparison
# ------------------------------------------------------------------ #
tab_compare, tab_sector, tab_correlation = st.tabs(
    ["Ticker Comparison", "Sector Analysis", "Correlation Matrix"]
)

with tab_compare:
    st.subheader("Performance Comparison")

    ticker_options = [t["ticker"] for t in all_tickers]
    selected_tickers = st.multiselect(
        "Select tickers to compare",
        ticker_options,
        default=[ticker_options[0]] if ticker_options else [],
        key="compare_tickers",
    )

    compare_range = st.checkbox("Filter date range", value=False, key="compare_range")
    start_date: date | None = None
    end_date: date | None = None
    if compare_range:
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start", value=date(2023, 1, 1), key="cmp_start")
        with col2:
            end_date = st.date_input("End", value=date.today(), key="cmp_end")

    if selected_tickers:
        try:
            with get_connection(config) as conn:
                prices_df = get_multi_ticker_candles_df(
                    conn, selected_tickers, start_date, end_date
                )
        except Exception as e:
            st.error(f"Failed to load comparison data: {e}")
            logger.error("Failed to load comparison data: %s", e)
            prices_df = pd.DataFrame()

        if not prices_df.empty:
            # Normalized price chart — one trace per ticker
            normalized = (prices_df / prices_df.iloc[0]) * 100
            fig = go.Figure()
            for ticker in normalized.columns:
                fig.add_trace(go.Scatter(
                    x=normalized.index,
                    y=normalized[ticker],
                    mode="lines",
                    name=ticker,
                ))
            fig.update_layout(
                title="Normalized Price Performance (Base = 100)",
                xaxis_title="Date",
                yaxis_title="Normalized Price",
                height=500,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig, width="stretch")

            # Performance metrics table
            st.subheader("Performance Metrics")
            metrics_list: list[dict] = []
            for ticker in selected_tickers:
                if ticker not in prices_df.columns:
                    continue
                series = prices_df[ticker].dropna()
                if series.empty:
                    continue
                cur = currency_map.get(ticker, "USD")
                returns = _calculate_returns(series)
                cum_returns = _calculate_cumulative_returns(returns)

                metrics_list.append({
                    "Ticker": ticker,
                    "Currency": cur,
                    "Current Price": _currency_fmt(series.iloc[-1], cur),
                    "Total Return": f"{cum_returns.iloc[-1] * 100:.1f}%" if not cum_returns.empty else "N/A",
                    "CAGR": f"{_calculate_cagr(series) * 100:.1f}%" if _calculate_cagr(series) is not None else "N/A",
                    "Max Drawdown": f"{_calculate_max_drawdown(series) * 100:.1f}%",
                    "Volatility (Ann.)": f"{returns.std() * np.sqrt(252) * 100:.1f}%" if not returns.empty else "N/A",
                })

            if metrics_list:
                st.dataframe(metrics_list, width="stretch", hide_index=True)

with tab_sector:
    st.subheader("Sector Breakdown")

    sector_data = [
        {"Sector": t.get("sector") or "Unknown", "Ticker": t["ticker"]}
        for t in tickers_with_stats
        if t.get("sector")
    ]

    if sector_data:
        sector_df = pd.DataFrame(sector_data)
        sector_counts = sector_df["Sector"].value_counts().reset_index()
        sector_counts.columns = ["Sector", "Count"]

        fig = go.Figure(data=[go.Pie(
            labels=sector_counts["Sector"],
            values=sector_counts["Count"],
            hole=0.3,
        )])
        fig.update_layout(
            title="Ticker Distribution by Sector",
            height=500,
        )
        st.plotly_chart(fig, width="stretch")

        with st.expander("Sector Details"):
            st.dataframe(sector_counts, width="stretch", hide_index=True)
    else:
        st.info("No sector data available.")

with tab_correlation:
    st.subheader("Correlation Matrix")

    corr_tickers = st.multiselect(
        "Select tickers for correlation analysis",
        ticker_options,
        default=ticker_options[:5] if len(ticker_options) >= 5 else ticker_options,
        key="corr_tickers",
    )

    corr_range = st.checkbox("Filter date range", value=False, key="corr_range")
    corr_start: date | None = None
    corr_end: date | None = None
    if corr_range:
        col1, col2 = st.columns(2)
        with col1:
            corr_start = st.date_input("Start", value=date(2023, 1, 1), key="corr_start")
        with col2:
            corr_end = st.date_input("End", value=date.today(), key="corr_end")

    if corr_tickers:
        try:
            with get_connection(config) as conn:
                corr_prices = get_multi_ticker_candles_df(
                    conn, corr_tickers, corr_start, corr_end
                )
        except Exception as e:
            st.error(f"Failed to load correlation data: {e}")
            logger.error("Failed to load correlation data: %s", e)
            corr_prices = pd.DataFrame()

        if not corr_prices.empty and len(corr_prices.columns) >= 2:
            returns_df = corr_prices.pct_change().dropna()
            corr_matrix = returns_df.corr()

            fig = go.Figure(data=go.Heatmap(
                z=corr_matrix.values,
                x=corr_matrix.columns,
                y=corr_matrix.index,
                text=corr_matrix.values.round(2),
                texttemplate="%{text}",
                textfont={"size": 12},
                colorscale="RdBu_r",
                zmin=-1,
                zmax=1,
                colorbar=dict(title="Correlation"),
            ))
            fig.update_layout(
                title="Daily Returns Correlation Matrix",
                height=600,
                xaxis_title="Ticker",
                yaxis_title="Ticker",
            )
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Need at least 2 tickers with data for correlation analysis.")
