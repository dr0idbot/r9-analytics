"""Data Ingestion page.

Renders the ticker roster, allows adding new tickers, and triggers
bulk or individual sync operations. All business logic is delegated
to shared/ functions.
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import streamlit as st

from shared.config import load_db_config
from shared.db import get_connection
from shared.ingest import fetch_ticker_meta, sync_ticker
from shared.queries import get_tickers_with_stats
from shared.roster import add_ticker_to_roster, read_roster

from dashboard.components import styled_df

logger = logging.getLogger(__name__)

st.title("Data Ingestion")
st.markdown("Manage ticker roster and sync market data from Yahoo Finance.")

config = load_db_config()

tab_roster, tab_add, tab_sync = st.tabs(["Ticker Roster", "Add Ticker", "Sync"])

# ------------------------------------------------------------------ #
# Tab 1: Ticker Roster
# ------------------------------------------------------------------ #
with tab_roster:
    st.subheader("Current Roster")
    try:
        with get_connection(config) as conn:
            tickers = get_tickers_with_stats(conn)
    except Exception as e:
        st.error(f"Failed to load roster: {e}")
        logger.error("Failed to load roster: %s", e)
        tickers = []

    if not tickers:
        st.info("Roster is empty. Add a ticker in the 'Add Ticker' tab.")
    else:
        st.metric("Total Tickers", len(tickers))
        styled_df(
            pd.DataFrame([
                {
                    "Ticker": t["ticker"],
                    "Name": t["name"] or "N/A",
                    "Sector": t["sector"] or "N/A",
                    "Candles": t["candle_count"],
                    "Dividends": t["dividend_count"],
                    "Splits": t["split_count"],
                    "Last Synced": str(t["last_synced_on"] or "-"),
                    "Last Candle": str(t["last_candle_date"] or "-"),
                }
                for t in tickers
            ]),
            width="stretch",
            hide_index=True,
        )

# ------------------------------------------------------------------ #
# Tab 2: Add Ticker
# ------------------------------------------------------------------ #
with tab_add:
    st.subheader("Add New Ticker")
    with st.form("add_ticker_form", clear_on_submit=True):
        symbol = st.text_input(
            "Ticker Symbol",
            placeholder="e.g. NVDA, TCS.NS",
            help="Enter a valid Yahoo Finance ticker symbol.",
        )
        submitted = st.form_submit_button("Add & Sync", type="primary")

    if submitted and symbol:
        symbol = symbol.upper().strip()
        with st.status(f"Adding {symbol}...", expanded=True) as status:
            try:
                st.write("Checking tradability on Yahoo Finance...")
                meta = fetch_ticker_meta(symbol)
                if meta is None:
                    status.update(label=f"{symbol} not found on Yahoo Finance", state="error")
                    st.error(f"**{symbol}** is not available on Yahoo Finance.")
                    st.stop()
                st.write(f"Found: {meta['name']} ({meta['exchange_name']})")

                added = add_ticker_to_roster(symbol)
                if not added:
                    status.update(label=f"{symbol} already in roster", state="complete")
                    st.warning(f"**{symbol}** is already in the roster.")
                    st.stop()

                st.write("Performing initial full sync...")
                with get_connection(config) as conn:
                    stats = sync_ticker(conn, symbol, force_full=True)

                status.update(label=f"{symbol} added and synced", state="complete")
                st.success(
                    f"**{symbol}** added and synced: "
                    f"{stats['candles']} candles, "
                    f"{stats['dividends']} dividends, "
                    f"{stats['splits']} splits"
                )
                st.rerun()

            except Exception as e:
                status.update(label=f"Failed to add {symbol}", state="error")
                st.error(f"Failed to add **{symbol}**: {e}")
                logger.error("Failed to add %s: %s", symbol, e)

# ------------------------------------------------------------------ #
# Tab 3: Sync
# ------------------------------------------------------------------ #
with tab_sync:
    st.subheader("Sync All Tickers")
    roster = read_roster()
    if not roster:
        st.info("Roster is empty. Add tickers first.")
    else:
        st.markdown(f"**{len(roster)}** tickers in roster. Last sync: "
                    f"{roster[0].get('last_synced_on', 'never')}")

        if st.button("Start Bulk Sync", type="primary", key="bulk_sync"):
            progress = st.progress(0)
            status_area = st.empty()
            results_area = st.container()

            failed: list[str] = []
            succeeded = 0

            for i, row in enumerate(roster):
                sym = row["ticker"]
                progress.progress((i) / len(roster))
                status_area.info(f"Syncing {sym} ({i + 1}/{len(roster)})...")

                try:
                    with get_connection(config) as conn:
                        stats = sync_ticker(conn, sym, resume_from=row["last_candle_date"])
                    succeeded += 1
                    with results_area:
                        st.success(
                            f"**{sym}**: +{stats['candles']} candles, "
                            f"+{stats['dividends']} div, +{stats['splits']} splits"
                        )
                except Exception as e:
                    failed.append(sym)
                    with results_area:
                        st.error(f"**{sym}**: {e}")
                    logger.error("Sync failed for %s: %s", sym, e)

            progress.progress(1.0)
            status_area.empty()

            st.markdown("---")
            st.markdown(
                f"**Sync complete:** {succeeded} succeeded, {len(failed)} failed"
            )
            if failed:
                st.warning(f"Failed: {', '.join(failed)}")
