"""Risk Analysis page.

Single-asset risk metrics and visualizations.
All computations delegate to shared/calculations.py.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.components import styled_df
from shared.calculations import (
    daily_returns,
    single_asset_risk,
)
from shared.config import load_db_config
from shared.db import get_connection
from shared.queries import get_all_tickers, get_candles_df

logger = logging.getLogger(__name__)

st.title("Risk Analysis")
st.markdown("Single-asset risk and risk-adjusted return metrics.")

config = load_db_config()

# Load available tickers
try:
    with get_connection(config) as conn:
        all_tickers = get_all_tickers(conn)
except Exception as e:
    st.error(f"Failed to load tickers: {e}")
    logger.error("Failed to load tickers: %s", e)
    st.stop()

if not all_tickers:
    st.info("No tickers available. Add data first.")
    st.stop()

ticker_options = [t["ticker"] for t in all_tickers]

# ------------------------------------------------------------------ #
# Ticker selector
# ------------------------------------------------------------------ #
selected_ticker = st.selectbox("Select Ticker", ticker_options, key="risk_ticker")

# ------------------------------------------------------------------ #
# Compute risk metrics
# ------------------------------------------------------------------ #
try:
    with get_connection(config) as conn:
        risk = single_asset_risk(conn, selected_ticker)
        returns = daily_returns(conn, selected_ticker)
        candles_df = get_candles_df(conn, selected_ticker)
except Exception as e:
    st.error(f"Failed to compute risk metrics: {e}")
    logger.error("Failed to compute risk metrics for %s: %s", selected_ticker, e)
    st.stop()

# ------------------------------------------------------------------ #
# Risk metrics cards
# ------------------------------------------------------------------ #
st.subheader(f"Metrics: {selected_ticker}")

# Phase 1: Risk
with st.container(border=True):
    st.markdown("**Risk Metrics**")
    with st.container(horizontal=True, wrap=True, gap="small"):
        st.metric("Realized Volatility", f"{risk['realized_volatility'] * 100:.2f}%", border=True, width="content")
        st.metric("Parkinson Volatility", f"{risk['parkinson_volatility'] * 100:.2f}%", border=True, width="content")
        st.metric("Garman-Klass Volatility", f"{risk['garman_klass_volatility'] * 100:.2f}%", border=True, width="content")
        st.metric("Max Drawdown", f"{risk['max_drawdown'] * 100:.2f}%", border=True, width="content")
        st.metric("Historical VaR (95%)", f"{risk['historical_var_95'] * 100:.2f}%", border=True, width="content")
        st.metric("Parametric VaR (95%)", f"{risk['parametric_var_95'] * 100:.2f}%", border=True, width="content")
        st.metric("CVaR (95%)", f"{risk['cvar_95'] * 100:.2f}%", border=True, width="content")
        st.metric("Semi-Deviation", f"{risk['semi_deviation'] * 100:.2f}%", border=True, width="content")
        st.metric("Downside Ratio", f"{risk['downside_ratio']:.4f}", border=True, width="content")

# Phase 2: Risk-Adjusted Return
with st.container(border=True):
    st.markdown("**Risk-Adjusted Return Metrics**")
    with st.container(horizontal=True, wrap=True, gap="small"):
        st.metric("Sharpe Ratio", f"{risk['sharpe_ratio']:.4f}", border=True, width="content")
        st.metric("Sortino Ratio", f"{risk['sortino_ratio']:.4f}", border=True, width="content")
        st.metric("Calmar Ratio", f"{risk['calmar_ratio']:.4f}", border=True, width="content")
        st.metric("Omega Ratio", f"{risk['omega_ratio']:.4f}", border=True, width="content")
        st.metric("Treynor Ratio", f"{risk['treynor_ratio']:.4f}", border=True, width="content")
        st.metric("Information Ratio", f"{risk['information_ratio']:.4f}", border=True, width="content")

# Phase 3: Market Risk
with st.container(border=True):
    st.markdown("**Market Risk Metrics** (vs SPY)")
    with st.container(horizontal=True, wrap=True, gap="small"):
        beta_val = risk.get("beta")
        alpha_val = risk.get("alpha")
        rsq_val = risk.get("r_squared")
        te_val = risk.get("tracking_error")
        st.metric("Beta", f"{beta_val:.4f}" if beta_val is not None else "N/A", border=True, width="content")
        st.metric("Alpha", f"{alpha_val:.4f}" if alpha_val is not None else "N/A", border=True, width="content")
        st.metric("R-Squared", f"{rsq_val:.4f}" if rsq_val is not None else "N/A", border=True, width="content")
        st.metric("Tracking Error", f"{te_val:.4f}" if te_val is not None else "N/A", border=True, width="content")

st.markdown("---")

# ------------------------------------------------------------------ #
# Charts
# ------------------------------------------------------------------ #
st.subheader("Visualizations")

chart_tab1, chart_tab2, chart_tab3 = st.tabs(["Price & Drawdown", "Returns Distribution", "Rolling Volatility"])

# Tab 1: Price & Drawdown
with chart_tab1:
    if candles_df.empty:
        st.info("No price data available.")
    else:
        prices = candles_df["close"]
        cummax = prices.cummax()
        drawdown = (prices - cummax) / cummax

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=prices.index, y=prices.values,
            name="Price", line={"color": "#1e66f5", "width": 2},
        ))
        fig.add_trace(go.Scatter(
            x=cummax.index, y=cummax.values,
            name="Peak", line={"color": "#df8e1d", "width": 1, "dash": "dot"},
        ))
        fig.update_layout(
            title=f"{selected_ticker} Price & Peak",
            xaxis_title="Date", yaxis_title="Price",
            height=400, legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        )
        st.plotly_chart(fig, width="stretch")

        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=drawdown.index, y=drawdown.values * 100,
            fill="tozeroy", name="Drawdown",
            line={"color": "#d20f39", "width": 1},
        ))
        fig2.update_layout(
            title=f"{selected_ticker} Drawdown",
            xaxis_title="Date", yaxis_title="Drawdown (%)",
            height=300,
        )
        st.plotly_chart(fig2, width="stretch")

# Tab 2: Returns Distribution
with chart_tab2:
    if returns.empty:
        st.info("Not enough data for returns distribution.")
    else:
        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=returns.values * 100,
            nbinsx=80,
            name="Daily Returns",
            marker_color="#1e66f5",
        ))

        # VaR line
        var_val = risk["historical_var_95"] * 100
        fig.add_vline(x=var_val, line_dash="dash", line_color="#d20f39",
                      annotation_text=f"VaR 95%: {var_val:.2f}%")

        # CVaR line
        cvar_val = risk["cvar_95"] * 100
        fig.add_vline(x=cvar_val, line_dash="dash", line_color="#e64553",
                      annotation_text=f"CVaR 95%: {cvar_val:.2f}%")

        fig.update_layout(
            title=f"{selected_ticker} Daily Returns Distribution",
            xaxis_title="Return (%)", yaxis_title="Frequency",
            height=400,
        )
        st.plotly_chart(fig, width="stretch")

# Tab 3: Rolling Volatility
with chart_tab3:
    if returns.empty or len(returns) < 30:
        st.info("Not enough data for rolling volatility.")
    else:
        window = st.slider("Rolling window (days)", 20, 120, 30, key="vol_window")
        rolling_vol = returns.rolling(window).std() * np.sqrt(252) * 100

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=rolling_vol.index, y=rolling_vol.values,
            name=f"{window}-day Rolling Vol",
            line={"color": "#fe640b", "width": 2},
        ))
        fig.add_hline(y=risk["realized_volatility"] * 100,
                      line_dash="dash", line_color="#1e66f5",
                      annotation_text="Full-period Vol")
        fig.update_layout(
            title=f"{selected_ticker} Rolling Annualized Volatility",
            xaxis_title="Date", yaxis_title="Volatility (%)",
            height=400,
        )
        st.plotly_chart(fig, width="stretch")

# ------------------------------------------------------------------ #
# Detailed metrics table
# ------------------------------------------------------------------ #
with st.expander("All Metrics (Detailed)"):
    metrics_df = pd.DataFrame([
        # Phase 1: Risk
        {"Category": "Risk", "Metric": "Realized Volatility", "Value": risk.get("realized_volatility"), "Unit": "%"},
        {"Category": "Risk", "Metric": "Parkinson Volatility", "Value": risk.get("parkinson_volatility"), "Unit": "%"},
        {"Category": "Risk", "Metric": "Garman-Klass Volatility", "Value": risk.get("garman_klass_volatility"), "Unit": "%"},
        {"Category": "Risk", "Metric": "Historical VaR (95%)", "Value": risk.get("historical_var_95"), "Unit": "%"},
        {"Category": "Risk", "Metric": "Parametric VaR (95%)", "Value": risk.get("parametric_var_95"), "Unit": "%"},
        {"Category": "Risk", "Metric": "CVaR (95%)", "Value": risk.get("cvar_95"), "Unit": "%"},
        {"Category": "Risk", "Metric": "Max Drawdown", "Value": risk.get("max_drawdown"), "Unit": "%"},
        {"Category": "Risk", "Metric": "Semi-Deviation", "Value": risk.get("semi_deviation"), "Unit": "%"},
        {"Category": "Risk", "Metric": "Downside Ratio", "Value": risk.get("downside_ratio"), "Unit": "ratio"},
        # Phase 2: Risk-Adjusted Return
        {"Category": "Return", "Metric": "Sharpe Ratio", "Value": risk.get("sharpe_ratio"), "Unit": "ratio"},
        {"Category": "Return", "Metric": "Sortino Ratio", "Value": risk.get("sortino_ratio"), "Unit": "ratio"},
        {"Category": "Return", "Metric": "Calmar Ratio", "Value": risk.get("calmar_ratio"), "Unit": "ratio"},
        {"Category": "Return", "Metric": "Treynor Ratio", "Value": risk.get("treynor_ratio"), "Unit": "ratio"},
        {"Category": "Return", "Metric": "Information Ratio", "Value": risk.get("information_ratio"), "Unit": "ratio"},
        {"Category": "Return", "Metric": "Omega Ratio", "Value": risk.get("omega_ratio"), "Unit": "ratio"},
        # Phase 3: Market Risk
        {"Category": "Market", "Metric": "Beta", "Value": risk.get("beta"), "Unit": "ratio"},
        {"Category": "Market", "Metric": "Alpha", "Value": risk.get("alpha"), "Unit": "ratio"},
        {"Category": "Market", "Metric": "R-Squared", "Value": risk.get("r_squared"), "Unit": "ratio"},
        {"Category": "Market", "Metric": "Tracking Error", "Value": risk.get("tracking_error"), "Unit": "ratio"},
    ])
    styled_df(
        metrics_df,
        column_config={
            "Value": st.column_config.NumberColumn("Value", format="%.4f", alignment="right"),
        },
        width="stretch",
        hide_index=True,
    )
