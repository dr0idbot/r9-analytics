"""Streamlit UI component helpers for the dashboard.

These functions compose Streamlit widgets. They contain NO business logic —
no yfinance calls, no DB queries, no CSV manipulation. They receive data
as arguments and render it.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import streamlit as st


def render_sync_status(stats: dict[str, Any], success: bool = True) -> None:
    """Display sync operation results.

    Args:
        stats: Dict with sync statistics (ticker, candles, dividends, splits).
        success: Whether the operation succeeded.
    """
    if success:
        st.success(
            f"Synced **{stats.get('ticker', '?')}**: "
            f"{stats.get('candles', 0)} candles, "
            f"{stats.get('dividends', 0)} dividends, "
            f"{stats.get('splits', 0)} splits"
        )
    else:
        st.error(f"Sync failed for **{stats.get('ticker', '?')}**: {stats.get('error', 'unknown')}")


def render_ticker_detail_card(ticker: dict[str, Any]) -> None:
    """Render a single ticker's metadata as a formatted card.

    Args:
        ticker: Dict with ticker metadata from queries.get_ticker_detail().
    """
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**{ticker.get('ticker', '?')}**")
        st.caption(ticker.get("name", "N/A"))
    with col2:
        st.markdown(f"**Sector:** {ticker.get('sector', 'N/A')}")
        st.markdown(f"**Industry:** {ticker.get('industry', 'N/A')}")
    with col3:
        st.markdown(f"**Exchange:** {ticker.get('exchange_name', 'N/A')}")
        st.markdown(f"**Country:** {ticker.get('country', 'N/A')}")

    meta_col1, meta_col2 = st.columns(2)
    with meta_col1:
        st.markdown(f"**Currency:** {ticker.get('currency', 'N/A')}")
        st.markdown(f"**Timezone:** {ticker.get('timezone', 'N/A')}")
        st.markdown(f"**Quote Type:** {ticker.get('quote_type', 'N/A')}")
    with meta_col2:
        st.markdown(f"**Last Synced:** {ticker.get('last_synced_on', 'N/A')}")
        st.markdown(f"**Last Candle:** {ticker.get('last_candle_date', 'N/A')}")
        st.markdown(f"**Active:** {ticker.get('is_active', False)}")


def render_date_range_filter(
    key_prefix: str = "filter",
    default_start: date | None = None,
    default_end: date | None = None,
) -> tuple[date | None, date | None]:
    """Render date range filter widgets in the sidebar.

    Args:
        key_prefix: Unique prefix for widget keys (avoids collisions).
        default_start: Default start date.
        default_end: Default end date.

    Returns:
        Tuple of (start_date, end_date).
    """
    with st.sidebar:
        st.markdown("### Date Range")
        use_range = st.checkbox("Filter by date range", value=False, key=f"{key_prefix}_use_range")
        if use_range:
            start = st.date_input(
                "Start date",
                value=default_start,
                key=f"{key_prefix}_start",
            )
            end = st.date_input(
                "End date",
                value=default_end,
                key=f"{key_prefix}_end",
            )
            return (start, end)
    return (None, None)


def render_metric_row(metrics: dict[str, Any]) -> None:
    """Render a row of st.metric cards.

    Args:
        metrics: Dict of {label: value} pairs to display.
    """
    cols = st.columns(len(metrics))
    for col, (label, value) in zip(cols, metrics.items()):
        with col:
            st.metric(label=label, value=value)


def render_empty_state(message: str = "No data available.") -> None:
    """Render an empty state placeholder.

    Args:
        message: Message to display.
    """
    st.info(message)
