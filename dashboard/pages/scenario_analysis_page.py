"""Scenario Analysis page — stress testing and scenario-based risk."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from shared.config import load_db_config
from shared.db import get_connection, get_all_tickers
from shared.calculations import scenario_analysis
from dashboard.components import styled_df

st.title("Scenario Analysis")

config = load_db_config()

# ── Ticker Selection ──────────────────────────────────────────────── #
tickers = get_all_tickers(get_connection(config))
if not tickers:
    st.info("No tickers in database.")
    st.stop()

selected_ticker = st.selectbox("Select Ticker", sorted(tickers))

# ── Compute ───────────────────────────────────────────────────────── #
if st.button("Run Scenario Analysis", type="primary"):
    with st.spinner("Running scenario analysis..."):
        result = scenario_analysis(get_connection(config), selected_ticker)
        st.session_state["scenario_result"] = result

result = st.session_state.get("scenario_result")

if result is None:
    st.info("Click 'Run Scenario Analysis' to compute metrics.")
    st.stop()

# ── Historical Stress Test ────────────────────────────────────────── #
st.subheader("Historical Stress Test")
st.caption("What would happen if current holdings experienced past crisis declines?")

if result["stress_test"]:
    stress_df = pd.DataFrame(result["stress_test"])

    # Bar chart of crisis returns
    fig = px.bar(
        stress_df,
        x="crisis",
        y="crisis_return",
        labels={"crisis": "Crisis", "crisis_return": "Return (%)"},
        text_auto=".1%",
        color="crisis_return",
        color_continuous_scale=["#d20f39", "#e64553", "#fe640b", "#df8e1d"],
    )
    fig.update_layout(
        title=f"{selected_ticker} Historical Crisis Returns",
        xaxis_title="Crisis", yaxis_title="Return (%)",
        height=350, showlegend=False,
    )
    st.plotly_chart(fig, width="stretch")

    # Table
    styled_stress = styled_df(
        result["stress_test"],
        column_config={
            "crisis_return": st.column_config.NumberColumn("Crisis Return", format="%.1%%"),
            "current_price": st.column_config.NumberColumn("Current Price", format="$%.2f"),
            "projected_price": st.column_config.NumberColumn("Projected Price", format="$%.2f"),
            "projected_loss": st.column_config.NumberColumn("Projected Loss", format="$%.2f"),
        },
        width="stretch",
        hide_index=True,
    )
    st.dataframe(styled_stress, use_container_width=True, hide_index=True)
else:
    st.info("No crisis data available.")

# ── Drawdown Duration ─────────────────────────────────────────────── #
st.subheader("Drawdown Duration")

dd = result["drawdown"]
with st.container(horizontal=True, wrap=True, gap="small"):
    st.metric("Max Drawdown Duration", f"{dd['max_drawdown_duration']} days", border=True, width="content")
    st.metric("Current Duration", f"{dd['current_drawdown_duration']} days", border=True, width="content")
    st.metric("Drawdown Events", f"{dd['drawdown_events']}", border=True, width="content")

# ── Win Rate & Profit Factor ──────────────────────────────────────── #
st.subheader("Consistency Metrics")

col1, col2 = st.columns(2)

with col1:
    wr = result["win_rate"]
    st.markdown("##### Win Rate (Monthly)")
    with st.container(horizontal=True, wrap=True, gap="small"):
        st.metric("Win Rate", f"{wr['win_rate']*100:.1f}%", border=True, width="content")
        st.metric("Winning", f"{wr['winning_periods']}", border=True, width="content")
        st.metric("Losing", f"{wr['losing_periods']}", border=True, width="content")

with col2:
    st.markdown("##### Profit Factor")
    if result["profit_factor"] is not None:
        st.metric("Profit Factor", f"{result['profit_factor']:.4f}", border=True, width="content")
        st.caption(">1 = profitable, <1 = unprofitable")
    else:
        st.metric("Profit Factor", "N/A", border=True, width="content")
        st.caption("No losses recorded")
