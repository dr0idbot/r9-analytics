"""Dashboard components package."""
from __future__ import annotations

import pandas as pd
import streamlit as st


def styled_df(df: pd.DataFrame, **kwargs):
    """Render a DataFrame with alternating row colors (zebra striping).

    Accepts the same keyword arguments as st.dataframe (width, hide_index, etc.).
    """
    hide_index = kwargs.pop("hide_index", True)

    def _zebra_css(row_idx: int) -> list[str]:
        bg = "background-color: rgba(138, 180, 250, 0.08)" if row_idx % 2 == 0 else ""
        return [bg] * len(df.columns)

    styler = df.style.apply(_zebra_css, axis=1)
    if hide_index:
        styler = styler.hide(axis="index")
    return st.dataframe(styler, **kwargs)
