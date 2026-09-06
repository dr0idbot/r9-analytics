"""Data Viewer page.

Browse and inspect ingested market data: OHLCV candles, dividends,
and splits. All queries are delegated to shared/ functions.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from shared.config import load_db_config
from shared.db import get_connection
from shared.queries import (
    get_all_tickers,
    get_candles_df,
    get_dividends,
    get_splits,
    get_ticker_detail,
)

logger = logging.getLogger(__name__)


def _render_candlestick_chart(df: pd.DataFrame, ticker: str) -> None:
    """Render a Plotly candlestick chart for OHLCV data."""
    if df.empty:
        st.info("No candle data to display.")
        return

    fig = go.Figure(
        data=[
            go.Candlestick(
                x=df.index,
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"],
                name=ticker,
            )
        ]
    )
    fig.update_layout(
        title=f"{ticker} -- Daily OHLCV",
        xaxis_title="Date",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        height=500,
    )
    st.plotly_chart(fig, width="stretch")


def _render_volume_chart(df: pd.DataFrame, ticker: str) -> None:
    """Render a Plotly bar chart for volume data."""
    if df.empty or df["volume"].isna().all():
        st.info("No volume data to display.")
        return

    fig = go.Figure(
        data=[
            go.Bar(
                x=df.index,
                y=df["volume"],
                name="Volume",
                marker_color="rgba(0, 123, 255, 0.6)",
            )
        ]
    )
    fig.update_layout(
        title=f"{ticker} -- Daily Volume",
        xaxis_title="Date",
        yaxis_title="Volume",
        height=300,
    )
    st.plotly_chart(fig, width="stretch")


st.title("Data Viewer")
st.markdown("Browse ingested market data for any tracked ticker.")

config = load_db_config()

try:
    with get_connection(config) as conn:
        all_tickers = get_all_tickers(conn)
except Exception as e:
    st.error(f"Failed to load tickers: {e}")
    logger.error("Failed to load tickers: %s", e)
    st.stop()

if not all_tickers:
    st.info("No tickers in database. Go to Data Ingestion to add some.")
    st.stop()

ticker_names = [f"{t['ticker']} -- {t['name'] or 'N/A'}" for t in all_tickers]
selected_label = st.selectbox("Select Ticker", ticker_names)
selected_ticker = selected_label.split(" -- ")[0]

# Date range filter (default: last 3 months)
today = date.today()
default_start = today - timedelta(days=90)
use_range = st.checkbox("Filter by date range", value=True)
start_date: date | None = None
end_date: date | None = None
if use_range:
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start date", value=default_start)
    with col2:
        end_date = st.date_input("End date", value=today)

try:
    with get_connection(config) as conn:
        ticker_detail = get_ticker_detail(conn, selected_ticker)
        candles_df = get_candles_df(conn, selected_ticker, start_date, end_date)
        dividends = get_dividends(conn, selected_ticker)
        splits = get_splits(conn, selected_ticker)
except Exception as e:
    st.error(f"Failed to load data for {selected_ticker}: {e}")
    logger.error("Failed to load data for %s: %s", selected_ticker, e)
    st.stop()

if ticker_detail:
    with st.expander("Ticker Info", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Name", ticker_detail.get("name", "N/A"))
        c2.metric("Sector", ticker_detail.get("sector", "N/A"))
        c3.metric("Exchange", ticker_detail.get("exchange_name", "N/A"))
        c4.metric("Country", ticker_detail.get("country", "N/A"))

tab_candles, tab_dividends, tab_splits = st.tabs(["Candles", "Dividends", "Splits"])

with tab_candles:
    if not candles_df.empty:
        st.metric("Trading Days", len(candles_df))
        _render_candlestick_chart(candles_df, selected_ticker)
        _render_volume_chart(candles_df, selected_ticker)

        with st.expander("Raw Data"):
            raw = candles_df.reset_index().tail(100).copy()
            raw["trade_date"] = raw["trade_date"].dt.strftime("%Y-%m-%d")
            st.dataframe(
                raw,
                width="stretch",
                hide_index=True,
            )
    else:
        st.info("No candle data for this ticker.")

with tab_dividends:
    if dividends:
        st.metric("Total Dividends", len(dividends))
        st.dataframe(
            [{"Date": d["pay_date"], "Amount": d["amount"]} for d in dividends],
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No dividend data for this ticker.")

with tab_splits:
    if splits:
        st.metric("Total Splits", len(splits))
        st.dataframe(
            [{"Date": s["split_date"], "Ratio": s["ratio"]} for s in splits],
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No split data for this ticker.")
