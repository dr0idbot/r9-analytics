"""R9 Analytics shared business logic.

This package contains ALL presentation-agnostic code:
- Database connection and query constants
- yfinance ingestion and sync logic
- CSV roster management
- Read-only queries for viewer/analytics

This package must NEVER import streamlit, plotly, or any UI library.
"""
from __future__ import annotations
