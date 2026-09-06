"""Portfolio Risk page — portfolio-level risk metrics."""
from __future__ import annotations

import streamlit as st

from shared.config import load_db_config
from shared.db import get_connection
from shared.portfolio import list_portfolios, get_portfolio_detail
from shared.calculations import (
    portfolio_risk,
    save_portfolio_risk,
    load_latest_portfolio_risk,
)
from dashboard.components import styled_df

st.title("Portfolio Risk")

config = load_db_config()

with get_connection(config) as conn:
    portfolios = list_portfolios(conn)

if not portfolios:
    st.info("No portfolios found. Create one in Portfolio Manager.")
    st.stop()

portfolio_options = {f"{p['name']} ({p['currency']}, {p['security_count']} securities)": p["id"] for p in portfolios}
selected_label = st.selectbox("Select Portfolio", list(portfolio_options.keys()))
portfolio_id = portfolio_options[selected_label]

with get_connection(config) as conn:
    detail = get_portfolio_detail(conn, portfolio_id)

# ── Compute / Load ────────────────────────────────────────────────── #
col_action1, col_action2 = st.columns(2)

with col_action1:
    if st.button("Compute Risk Metrics", type="primary", use_container_width=True):
        with st.spinner("Computing portfolio risk..."):
            with get_connection(config) as conn:
                risk = portfolio_risk(conn, portfolio_id)
            st.session_state["portfolio_risk"] = risk

with col_action2:
    if st.button("Load Saved Metrics", use_container_width=True):
        with get_connection(config) as conn:
            saved = load_latest_portfolio_risk(conn, portfolio_id)
        if saved:
            st.session_state["portfolio_risk_saved"] = saved
        else:
            st.warning("No saved metrics found.")

risk = st.session_state.get("portfolio_risk")
saved = st.session_state.get("portfolio_risk_saved")

# ── Saved Metrics ─────────────────────────────────────────────────── #
if saved:
    st.subheader("Last Saved Metrics")
    with st.container(horizontal=True, wrap=True, gap="small"):
        st.metric("Saved At", str(saved["calc_time"])[:19], border=True, width="content")
        if saved["portfolio_beta"] is not None:
            st.metric("Portfolio Beta", f"{saved['portfolio_beta']:.4f}", border=True, width="content")
        if saved["portfolio_volatility"] is not None:
            st.metric("Portfolio Volatility", f"{saved['portfolio_volatility']*100:.2f}%", border=True, width="content")

# ── Current Metrics ───────────────────────────────────────────────── #
if risk:
    st.subheader("Current Risk Metrics")

    st.markdown("#### Market Risk")
    with st.container(horizontal=True, wrap=True, gap="small"):
        if risk["portfolio_beta"] is not None:
            st.metric("Portfolio Beta", f"{risk['portfolio_beta']:.4f}", border=True, width="content")
        else:
            st.metric("Portfolio Beta", "N/A", border=True, width="content")
        if risk["portfolio_volatility"] is not None:
            st.metric("Portfolio Volatility", f"{risk['portfolio_volatility']*100:.2f}%", border=True, width="content")
        else:
            st.metric("Portfolio Volatility", "N/A", border=True, width="content")

    st.markdown("#### Risk Metrics")
    with st.container(horizontal=True, wrap=True, gap="small"):
        if risk["portfolio_var_95"] is not None:
            st.metric("VaR (95%)", f"{risk['portfolio_var_95']*100:.2f}%", border=True, width="content")
        else:
            st.metric("VaR (95%)", "N/A", border=True, width="content")
        if risk["portfolio_cvar_95"] is not None:
            st.metric("CVaR (95%)", f"{risk['portfolio_cvar_95']*100:.2f}%", border=True, width="content")
        else:
            st.metric("CVaR (95%)", "N/A", border=True, width="content")

    st.markdown("#### Diversification")
    with st.container(horizontal=True, wrap=True, gap="small"):
        if risk["diversification_ratio"] is not None:
            st.metric("Diversification Ratio", f"{risk['diversification_ratio']:.4f}", border=True, width="content")
        else:
            st.metric("Diversification Ratio", "N/A", border=True, width="content")
        st.metric("Concentration Index", f"{risk['concentration_index']:.4f}", border=True, width="content")

    # ── Value Contributions ───────────────────────────────────────── #
    if risk["value_contributions"]:
        st.markdown("#### Value Contributions")
        vc_df = styled_df(
            risk["value_contributions"],
            column_config={
                "weight": st.column_config.NumberColumn("Weight", format="%.2%%", alignment="right"),
                "annual_return": st.column_config.NumberColumn("Annual Return", format="%.2%%", alignment="right"),
                "contribution": st.column_config.NumberColumn("Contribution", format="%.4%%", alignment="right"),
            },
            width="stretch",
            hide_index=True,
        )
        st.dataframe(vc_df, use_container_width=True, hide_index=True)

    # ── Save ──────────────────────────────────────────────────────── #
    st.divider()
    if st.button("Save Portfolio Risk Metrics", type="primary"):
        with st.spinner("Saving..."):
            with get_connection(config) as conn:
                save_portfolio_risk(conn, portfolio_id)
            st.success("Portfolio risk metrics saved!")
