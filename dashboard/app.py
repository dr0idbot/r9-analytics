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

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* ---- Base text ---- */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* ---- Headings ---- */
h1, h2, h3, h4, h5, h6 {
    font-family: 'Inter', sans-serif;
    font-weight: 600;
    letter-spacing: -0.02em;
}

/* ---- Numbers / metrics ---- */
[data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
    letter-spacing: -0.03em;
    font-size: 1.1rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

[data-testid="stMetricLabel"] {
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #6b7280;
}

[data-testid="stMetricDelta"] {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 500;
}

/* ---- Dataframe cells ---- */
.stDataFrame [data-testid="stDataFrameCell"],
.stDataFrame td,
.stDataFrame th {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.85rem;
}

/* ---- Sidebar ---- */
[data-testid="stSidebar"] {
    font-family: 'Inter', sans-serif;
}

[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
    font-weight: 400;
}

/* ---- Tabs ---- */
button[data-baseweb="tab"] {
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    letter-spacing: -0.01em;
}

/* ---- Captions / small text ---- */
small, .stCaption {
    font-family: 'Inter', sans-serif;
    font-weight: 300;
}

/* ---- Code / monospace ---- */
code, pre, .stCode {
    font-family: 'JetBrains Mono', monospace;
}
</style>
""", unsafe_allow_html=True)

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
