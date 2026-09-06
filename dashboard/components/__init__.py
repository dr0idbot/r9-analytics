"""Dashboard components package."""
from __future__ import annotations

import pandas as pd
import streamlit as st


def styled_df(df: pd.DataFrame, **kwargs):
    """Render a DataFrame with zebra striping and right-aligned numbers.

    Accepts the same keyword arguments as st.dataframe (width, hide_index, etc.).
    """
    hide_index = kwargs.pop("hide_index", True)

    def _zebra_css(row):
        idx = row.name
        bg = "background-color: rgba(138, 180, 250, 0.08)" if idx % 2 == 0 else ""
        return [bg] * len(df.columns)

    def _align_numbers(col):
        if pd.api.types.is_numeric_dtype(col.dtype):
            return ["text-align: right"] * len(col)
        return [""] * len(col)

    styler = df.style.apply(_zebra_css, axis=1).apply(_align_numbers, axis=0)
    if hide_index:
        styler = styler.hide(axis="index")
    return st.dataframe(styler, **kwargs)
