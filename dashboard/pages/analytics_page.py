"""Data Analytics page.

Calculations, performance metrics, and analytical charts.
All computations use data from shared/ queries and pandas/plotly.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from shared.config import PROJECT_ROOT, load_db_config
from shared.db import get_connection
from shared.queries import (
    get_all_tickers,
    get_multi_ticker_candles_df,
    get_sync_summary,
    get_tickers_with_stats,
)

from dashboard.components import styled_df

logger = logging.getLogger(__name__)

_CURRENCY_FILE = PROJECT_ROOT / "config" / "currency_symbols.json"
_CURRENCY_SYMBOLS: dict[str, str] = json.loads(_CURRENCY_FILE.read_text())


def _currency_fmt(amount: float, currency: str | None) -> str:
    symbol = _CURRENCY_SYMBOLS.get((currency or "USD").upper(), _CURRENCY_SYMBOLS["USD"])
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

ticker_options = [t["ticker"] for t in all_tickers]

# ------------------------------------------------------------------ #
# Tabs
# ------------------------------------------------------------------ #
tab_compare, tab_sector = st.tabs(["Ticker Comparison", "Sector Breakdown"])

# ================================================================== #
# Tab 1: Ticker Comparison
# ================================================================== #
with tab_compare:
    st.subheader("Performance Comparison")

    selected_tickers = st.multiselect(
        "Select tickers to compare",
        ticker_options,
        default=[ticker_options[0]] if ticker_options else [],
        key="compare_tickers",
    )

    today = date.today()
    default_start = today - pd.Timedelta(days=90)
    compare_range = st.checkbox("Filter date range", value=True, key="compare_range")
    start_date: date | None = None
    end_date: date | None = None
    if compare_range:
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start", value=default_start, key="cmp_start")
        with col2:
            end_date = st.date_input("End", value=today, key="cmp_end")

    if not selected_tickers:
        st.info("Select at least one ticker above.")
    else:
        try:
            with get_connection(config) as conn:
                prices_df = get_multi_ticker_candles_df(
                    conn, selected_tickers, start_date, end_date
                )
        except Exception as e:
            st.error(f"Failed to load comparison data: {e}")
            logger.error("Failed to load comparison data: %s", e)
            prices_df = pd.DataFrame()

        if prices_df.empty:
            st.info("No data found for selected tickers.")
        else:
            filled = prices_df.ffill().dropna(axis=1, how="all")

            if filled.empty:
                st.info("No overlapping data for selected tickers.")
            else:
                # Normalize to base 100
                normalized = (filled / filled.iloc[0]) * 100

                # Melt to long format for px.line (each ticker becomes a separate line)
                melted = normalized.reset_index().melt(
                    id_vars="trade_date", var_name="Ticker", value_name="Price"
                )

                fig = px.line(
                    melted,
                    x="trade_date",
                    y="Price",
                    color="Ticker",
                    title="Normalized Price Performance (Base = 100)",
                    labels={"trade_date": "Date", "Price": "Normalized Price"},
                )
                fig.update_layout(
                    height=500,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                )
                st.plotly_chart(fig, width="stretch")

                # --- Metrics table ---
                st.subheader("Performance Metrics")
                metrics_list: list[dict] = []
                for ticker in filled.columns:
                    series = filled[ticker].dropna()
                    if series.empty:
                        continue
                    cur = currency_map.get(ticker, "USD")
                    returns = _calculate_returns(series)
                    cum_returns = _calculate_cumulative_returns(returns)
                    metrics_list.append({
                        "Ticker": ticker,
                        "Currency": cur,
                        "Current Price": series.iloc[-1],
                        "Total Return (%)": cum_returns.iloc[-1] * 100 if not cum_returns.empty else None,
                        "CAGR (%)": _calculate_cagr(series) * 100 if _calculate_cagr(series) is not None else None,
                        "Max Drawdown (%)": _calculate_max_drawdown(series) * 100,
                        "Volatility (Ann. %)": returns.std() * np.sqrt(252) * 100 if not returns.empty else None,
                    })

                if metrics_list:
                    metrics_df = pd.DataFrame(metrics_list)
                    styler = metrics_df.style
                    styler = styler.format({
                        "Current Price": "${:,.2f}",
                        "Total Return (%)": "{:.1f}%",
                        "CAGR (%)": "{:.1f}%",
                        "Max Drawdown (%)": "{:.1f}%",
                        "Volatility (Ann. %)": "{:.1f}%",
                    }, na_rep="N/A")
                    styler = styler.apply(
                        lambda col: ["text-align: right"] * len(col)
                        if pd.api.types.is_numeric_dtype(col.dtype)
                        else [""],
                        axis=0,
                    )
                    st.dataframe(styler, width="stretch", hide_index=True)

# ================================================================== #
# Tab 2: Sector Breakdown
# ================================================================== #
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
        fig.update_layout(title="Ticker Distribution by Sector", height=500)
        st.plotly_chart(fig, width="stretch")

        with st.expander("Sector Details"):
            styled_df(sector_counts, width="stretch", hide_index=True)
    else:
        st.info("No sector data available.")
