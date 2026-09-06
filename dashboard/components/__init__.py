"""Dashboard components package."""
from __future__ import annotations

import pandas as pd
import streamlit as st


def styled_df(df, **kwargs):
    """Render a DataFrame with zebra striping.

    Accepts the same keyword arguments as st.dataframe (width, hide_index, etc.).
    Pass ``column_config`` with ``alignment="right"`` for numeric columns
    to right-align data cells (headers are not affected — Streamlit limitation).
    """
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    hide_index = kwargs.pop("hide_index", True)

    def _zebra_css(row):
        idx = row.name
        bg = "background-color: rgba(138, 180, 250, 0.08)" if idx % 2 == 0 else ""
        return [bg] * len(df.columns)

    styler = df.style.apply(_zebra_css, axis=1)
    if hide_index:
        styler = styler.hide(axis="index")
    return st.dataframe(styler, **kwargs)
