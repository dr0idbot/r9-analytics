"""Dashboard components package."""
from __future__ import annotations

import pandas as pd
import streamlit as st


def styled_df(df: pd.DataFrame, **kwargs):
    """Render a DataFrame with zebra striping and right-aligned numbers.

    Accepts the same keyword arguments as st.dataframe (width, hide_index, etc.).
    """
    hide_index = kwargs.pop("hide_index", True)

    num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c].dtype)]

    def _zebra_css(row):
        idx = row.name
        bg = "background-color: rgba(138, 180, 250, 0.08)" if idx % 2 == 0 else ""
        return [bg] * len(df.columns)

    def _align_cells(col):
        if pd.api.types.is_numeric_dtype(col.dtype):
            return ["text-align: right"] * len(col)
        return [""]

    styler = df.style.apply(_zebra_css, axis=1).apply(_align_cells, axis=0)

    if num_cols:
        styler = styler.set_properties(
            subset=num_cols,
            **{"text-align": "right"},
        )
        styler = styler.set_table_styles(
            [{"selector": "th", "props": [("text-align", "left")]}],
            overwrite=True,
        )
        for c in num_cols:
            idx = df.columns.get_loc(c) + 1
            styler = styler.set_table_styles(
                [{"selector": f"th:nth-child({idx})", "props": [("text-align", "right")]}],
                overwrite=False,
            )

    if hide_index:
        styler = styler.hide(axis="index")
    return st.dataframe(styler, **kwargs)
