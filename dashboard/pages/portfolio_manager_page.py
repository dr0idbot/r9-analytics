"""Portfolio Manager page.

Create, view, and manage portfolios and their securities.
All business logic is delegated to shared/ functions.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from shared.config import load_db_config
from shared.calculations import portfolio_exposure
from shared.db import get_connection, list_currencies
from shared.portfolio import (
    PortfolioError,
    add_security,
    create_portfolio,
    delete_portfolio,
    get_portfolio_detail,
    list_portfolios,
    remove_security,
)

from dashboard.components import styled_df

logger = logging.getLogger(__name__)

st.title("Portfolio Manager")
st.markdown("Create and manage portfolios. All securities must share the same currency.")

config = load_db_config()

# ------------------------------------------------------------------ #
# Load data
# ------------------------------------------------------------------ #
try:
    with get_connection(config) as conn:
        portfolios = list_portfolios(conn)
        currencies = list_currencies(conn)
except Exception as e:
    st.error(f"Failed to load data: {e}")
    logger.error("Failed to load data: %s", e)
    st.stop()

# ------------------------------------------------------------------ #
# Sidebar: Create Portfolio
# ------------------------------------------------------------------ #
with st.sidebar:
    st.subheader("Create Portfolio")
    with st.form("create_portfolio", clear_on_submit=True):
        name = st.text_input("Portfolio Name", placeholder="e.g. Growth Portfolio")
        currency = st.selectbox("Currency", currencies)
        submitted = st.form_submit_button("Create", type="primary")

    if submitted and name:
        try:
            with get_connection(config) as conn:
                pid = create_portfolio(conn, name, currency)
            st.success(f"Created portfolio '{name}' (id={pid})")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to create portfolio: {e}")
            logger.error("Failed to create portfolio: %s", e)

# ------------------------------------------------------------------ #
# Main content
# ------------------------------------------------------------------ #
if not portfolios:
    st.info("No portfolios yet. Create one in the sidebar.")
    st.stop()

# Portfolio selector
portfolio_options = {f"{p['name']} ({p['currency']}, {p['security_count']} securities)": p["id"] for p in portfolios}
selected_label = st.selectbox("Select Portfolio", list(portfolio_options.keys()))
selected_id = portfolio_options[selected_label]

# Load portfolio detail
try:
    with get_connection(config) as conn:
        detail = get_portfolio_detail(conn, selected_id)
except Exception as e:
    st.error(f"Failed to load portfolio: {e}")
    logger.error("Failed to load portfolio: %s", e)
    st.stop()

if detail is None:
    st.error("Portfolio not found.")
    st.stop()

# ------------------------------------------------------------------ #
# Portfolio info
# ------------------------------------------------------------------ #
c1, c2, c3, c4 = st.columns(4)
c1.metric("Name", detail["name"])
c2.metric("Currency", detail["currency"])
c3.metric("Securities", len(detail["securities"]))
c4.metric("Total Value", f"{detail['currency']} {detail['total_value']:,.2f}")

# ------------------------------------------------------------------ #
# Tabs
# ------------------------------------------------------------------ #
tab_securities, tab_add, tab_exposure = st.tabs(["Securities", "Add Security", "Exposure"])

# ------------------------------------------------------------------ #
# Tab 1: Securities
# ------------------------------------------------------------------ #
with tab_securities:
    st.subheader("Portfolio Securities")

    if not detail["securities"]:
        st.info("No securities in this portfolio. Add some in the 'Add Security' tab.")
    else:
        # Display securities table
        sec_df = pd.DataFrame(detail["securities"])
        sec_df["buy_price_fmt"] = sec_df["buy_price"].apply(lambda x: f"{x:,.2f}")
        sec_df["units_fmt"] = sec_df["units"].apply(lambda x: f"{x:,.4f}")
        sec_df["market_value_fmt"] = sec_df["market_value"].apply(lambda x: f"{x:,.2f}")
        sec_df["weight_pct"] = sec_df["weight"].apply(lambda x: f"{x * 100:.2f}%")
        styled_df(
            sec_df[["ticker", "name", "sector", "buy_price_fmt", "units_fmt", "market_value_fmt", "weight_pct"]].rename(
                columns={
                    "buy_price_fmt": "Buy Price",
                    "units_fmt": "Units",
                    "market_value_fmt": "Market Value",
                    "weight_pct": "Weight",
                }
            ),
            width="stretch",
            hide_index=True,
        )

        # Remove security
        st.subheader("Remove Security")
        remove_ticker = st.selectbox(
            "Select ticker to remove",
            [s["ticker"] for s in detail["securities"]],
            key="remove_ticker",
        )
        if st.button("Remove", type="secondary"):
            try:
                with get_connection(config) as conn:
                    remove_security(conn, selected_id, remove_ticker)
                st.success(f"Removed {remove_ticker}")
                st.rerun()
            except Exception as e:
                st.error(f"Failed: {e}")

        # Delete portfolio
        st.subheader("Danger Zone")
        if st.button("Delete Portfolio", type="secondary"):
            st.session_state["confirm_delete"] = True

        if st.session_state.get("confirm_delete"):
            st.warning(f"Are you sure you want to delete '{detail['name']}'?")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Yes, delete", type="primary"):
                    try:
                        with get_connection(config) as conn:
                            delete_portfolio(conn, selected_id)
                        st.success(f"Deleted portfolio '{detail['name']}'")
                        st.session_state["confirm_delete"] = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed: {e}")
            with col2:
                if st.button("Cancel"):
                    st.session_state["confirm_delete"] = False
                    st.rerun()

# ------------------------------------------------------------------ #
# Tab 2: Add Security
# ------------------------------------------------------------------ #
with tab_add:
    st.subheader("Add Security")
    st.info(f"Only tickers with currency {detail['currency']} can be added to this portfolio.")

    try:
        with get_connection(config) as conn:
            all_tickers = conn.execute(
                "SELECT ticker, name, sector, currency FROM market.tickers ORDER BY ticker"
            ).fetchall()
    except Exception as e:
        st.error(f"Failed to load tickers: {e}")
        logger.error("Failed to load tickers: %s", e)
        all_tickers = []

    # Filter tickers by portfolio currency
    matching_tickers = [
        {"ticker": t[0], "name": t[1], "sector": t[2], "currency": t[3]}
        for t in all_tickers
        if t[3] and t[3].upper() == detail["currency"].upper()
    ]

    if not matching_tickers:
        st.warning(f"No tickers found with currency {detail['currency']}.")
    else:
        # Exclude already-added tickers
        existing_tickers = {s["ticker"] for s in detail["securities"]}
        available_tickers = [t for t in matching_tickers if t["ticker"] not in existing_tickers]

        if not available_tickers:
            st.info("All available tickers are already in this portfolio.")
        else:
            ticker_options = {f"{t['ticker']} — {t['name']} ({t['sector']})": t["ticker"] for t in available_tickers}
            selected_ticker_label = st.selectbox("Select Ticker", list(ticker_options.keys()))
            selected_ticker = ticker_options[selected_ticker_label]

            col1, col2 = st.columns(2)
            with col1:
                buy_price = st.number_input(
                    "Buy Price per Unit",
                    min_value=0.01,
                    value=100.0,
                    step=0.01,
                    format="%.2f",
                )
            with col2:
                units = st.number_input(
                    "Number of Units",
                    min_value=0.01,
                    value=1.0,
                    step=0.01,
                    format="%.4f",
                )

            buy_date = st.date_input("Buy Date", value=date.today())

            if st.button("Add Security", type="primary"):
                try:
                    with get_connection(config) as conn:
                        add_security(conn, selected_id, selected_ticker, buy_price, buy_date, units)
                    st.success(f"Added {selected_ticker}")
                    st.rerun()
                except PortfolioError as e:
                    st.error(f"Failed: {e}")

# ------------------------------------------------------------------ #
# Tab 3: Exposure
# ------------------------------------------------------------------ #
with tab_exposure:
    st.subheader("Portfolio Exposure")

    if not detail["securities"]:
        st.info("No securities to analyze.")
    else:
        import plotly.express as px

        try:
            with get_connection(config) as conn:
                exposure = portfolio_exposure(conn, selected_id)
        except Exception as e:
            st.error(f"Failed to calculate exposure: {e}")
            logger.error("Failed to calculate exposure: %s", e)
            st.stop()

        # Sector exposure
        st.markdown("#### Sector Exposure")
        if exposure["sector"]:
            sector_df = pd.DataFrame(exposure["sector"])
            sector_df["weight_pct"] = sector_df["weight"] * 100

            col1, col2 = st.columns([1, 1])
            with col1:
                fig = px.pie(
                    sector_df,
                    values="weight",
                    names="sector",
                    title="Sector Allocation",
                )
                st.plotly_chart(fig, width="stretch")
            with col2:
                styled_df(
                    sector_df[["sector", "weight_pct", "tickers"]].rename(columns={"weight_pct": "Weight (%)"}),
                    width="stretch",
                    hide_index=True,
                )

        # Industry exposure
        st.markdown("#### Industry Exposure")
        if exposure["industry"]:
            industry_df = pd.DataFrame(exposure["industry"])
            industry_df["weight_pct"] = industry_df["weight"] * 100

            col1, col2 = st.columns([1, 1])
            with col1:
                fig = px.bar(
                    industry_df,
                    x="weight_pct",
                    y="industry",
                    orientation="h",
                    title="Industry Allocation",
                    labels={"weight_pct": "Weight (%)", "industry": ""},
                )
                fig.update_layout(yaxis=dict(autorange="reversed"))
                st.plotly_chart(fig, width="stretch")
            with col2:
                styled_df(
                    industry_df[["industry", "weight_pct", "tickers"]].rename(columns={"weight_pct": "Weight (%)"}),
                    width="stretch",
                    hide_index=True,
                )
