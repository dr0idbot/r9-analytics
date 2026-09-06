"""Portfolio Exposure page.

View detailed exposure breakdowns for portfolios.
All business logic is delegated to shared/ functions.
"""
from __future__ import annotations

import logging

import pandas as pd
import plotly.express as px
import streamlit as st

from shared.config import load_db_config
from shared.calculations import portfolio_exposure
from shared.db import get_connection
from shared.portfolio import get_portfolio_detail, list_portfolios

from dashboard.components import styled_df

logger = logging.getLogger(__name__)

st.title("Portfolio Exposure")
st.markdown("Analyze sector and industry exposure across your portfolios.")

config = load_db_config()

# ------------------------------------------------------------------ #
# Load data
# ------------------------------------------------------------------ #
try:
    with get_connection(config) as conn:
        portfolios = list_portfolios(conn)
except Exception as e:
    st.error(f"Failed to load portfolios: {e}")
    logger.error("Failed to load portfolios: %s", e)
    st.stop()

if not portfolios:
    st.info("No portfolios yet. Create one in Portfolio Manager.")
    st.stop()

# Portfolio selector
portfolio_options = {f"{p['name']} ({p['currency']})": p["id"] for p in portfolios}
selected_label = st.selectbox("Select Portfolio", list(portfolio_options.keys()))
selected_id = portfolio_options[selected_label]

# Load portfolio detail
try:
    with get_connection(config) as conn:
        detail = get_portfolio_detail(conn, selected_id)
        exposure = portfolio_exposure(conn, selected_id)
except Exception as e:
    st.error(f"Failed to load portfolio: {e}")
    logger.error("Failed to load portfolio: %s", e)
    st.stop()

if detail is None:
    st.error("Portfolio not found.")
    st.stop()

# ------------------------------------------------------------------ #
# Summary metrics
# ------------------------------------------------------------------ #
st.subheader("Portfolio Summary")
with st.container(border=True):
    with st.container(horizontal=True, wrap=True, gap="small"):
        st.metric("Name", detail["name"], border=True, width="content")
        st.metric("Currency", detail["currency"], border=True, width="content")
        st.metric("Securities", len(detail["securities"]), border=True, width="content")
        st.metric("Total Value", f"{detail['currency']} {detail['total_value']:,.2f}", border=True, width="content")

st.markdown("---")

# ------------------------------------------------------------------ #
# Sector Exposure
# ------------------------------------------------------------------ #
st.subheader("Sector Exposure")

if not exposure["sector"]:
    st.info("No sector data available.")
else:
    sector_df = pd.DataFrame(exposure["sector"])
    sector_df["weight_pct"] = sector_df["weight"] * 100

    col1, col2 = st.columns([2, 1])
    with col1:
        fig = px.pie(
            sector_df,
            values="weight",
            names="sector",
            title="Sector Allocation",
            hole=0.3,
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, width="stretch")
    with col2:
        styled_df(
            sector_df[["sector", "weight_pct", "tickers"]].rename(
                columns={"weight_pct": "Weight (%)"}
            ),
            column_config={
                "Weight (%)": st.column_config.NumberColumn(alignment="right"),
            },
            width="stretch",
            hide_index=True,
        )

# ------------------------------------------------------------------ #
# Industry Exposure
# ------------------------------------------------------------------ #
st.subheader("Industry Exposure")

if not exposure["industry"]:
    st.info("No industry data available.")
else:
    industry_df = pd.DataFrame(exposure["industry"])
    industry_df["weight_pct"] = industry_df["weight"] * 100

    col1, col2 = st.columns([2, 1])
    with col1:
        fig = px.bar(
            industry_df,
            x="weight_pct",
            y="industry",
            orientation="h",
            title="Industry Allocation",
            labels={"weight_pct": "Weight (%)", "industry": ""},
        )
        fig.update_layout(
            yaxis=dict(autorange="reversed"),
            height=max(300, len(industry_df) * 40),
        )
        st.plotly_chart(fig, width="stretch")
    with col2:
        styled_df(
            industry_df[["industry", "weight_pct", "tickers"]].rename(
                columns={"weight_pct": "Weight (%)"}
            ),
            column_config={
                "Weight (%)": st.column_config.NumberColumn(alignment="right"),
            },
            width="stretch",
            hide_index=True,
        )

# ------------------------------------------------------------------ #
# Detailed Securities
# ------------------------------------------------------------------ #
with st.expander("View All Securities"):
    if detail["securities"]:
        sec_df = pd.DataFrame(detail["securities"])
        styled_df(
            sec_df[["ticker", "name", "sector", "industry", "currency", "buy_price", "units", "market_value", "weight"]].rename(
                columns={"buy_price": "Buy Price", "units": "Units", "market_value": "Market Value", "weight": "Weight"}
            ),
            column_config={
                "Buy Price": st.column_config.NumberColumn(alignment="right"),
                "Units": st.column_config.NumberColumn(alignment="right"),
                "Market Value": st.column_config.NumberColumn(alignment="right"),
                "Weight": st.column_config.NumberColumn(alignment="right"),
            },
            width="stretch",
            hide_index=True,
        )
