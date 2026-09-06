"""Streamlit entry point for R9 Analytics dashboard.

Run with:
    streamlit run dashboard/app.py

This file sets up page config, sidebar navigation, and delegates to
page-specific render() functions. It contains NO business logic.
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="R9 Analytics",
    layout="wide",
    initial_sidebar_state="expanded",
)

pg = st.navigation(
    {
        "Market Data": [
            st.Page("pages/ingestion_page.py", title="Data Ingestion", icon=":material/database:"),
            st.Page("pages/viewer_page.py", title="Data Viewer", icon=":material/visibility:"),
            st.Page("pages/analytics_page.py", title="Data Analytics", icon=":material/analytics:"),
        ]
    }
)

pg.run()
