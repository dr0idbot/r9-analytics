# R9-Analytics Streamlit Dashboard — Restructuring Plan

## Goal

Transform the current CLI-only market data ingestion tool into a Streamlit-based dashboard with three sections — **Data Ingestion**, **Data Viewer**, and **Data Analytics** — while keeping business logic cleanly separated from the presentation layer so Streamlit can be swapped out in the future.

---

## Current State

```
r9-analytics/
└── data-ingestion-module/
    ├── config/          # dbconf.yaml, tickers.csv
    ├── sql/             # create_tables.sql
    └── src/
        ├── main.py      # CLI entry point (interactive menu)
        ├── db.py        # DB connection + all SQL constants
        ├── ingest.py    # yfinance fetch + smart-sync logic
        ├── roster.py    # CSV roster read/write
        └── logging_setup.py
```

- Single CLI entry point (`main.py`) with interactive menu
- Business logic (fetching, syncing, DB writes) lives in `ingest.py`, `db.py`, `roster.py`
- No web server, no UI, no visualization
- Dependencies: `psycopg`, `pyyaml`, `yfinance`

---

## Target State

```
r9-analytics/
├── shared/                          # Business logic (presentation-agnostic)
│   ├── __init__.py
│   ├── config.py                    # Centralised config loader (DB, paths)
│   ├── db.py                        # DB connection + SQL constants (from src/db.py)
│   ├── ingest.py                    # yfinance fetch + sync (from src/ingest.py)
│   ├── roster.py                    # CSV roster ops (from src/roster.py)
│   ├── queries.py                   # Read-only queries for viewer/analytics
│   └── logging_setup.py             # Coloured logging (from src/logging_setup.py)
│
├── cli/                             # Original CLI interface (untouched logic)
│   └── main.py                      # Refactored to import from shared/
│
├── dashboard/                       # Streamlit presentation layer
│   ├── app.py                       # Streamlit entry point (sidebar nav)
│   ├── pages/
│   │   ├── 1_Data_Ingestion.py      # Add tickers, trigger sync, view status
│   │   ├── 2_Data_Viewer.py         # Browse/query ingested data
│   │   └── 3_Data_Analytics.py      # Charts, calculations, results (Plotly)
│   └── components/
│       ├── ingestion_ui.py          # Ingestion-specific widgets/helpers
│       ├── viewer_ui.py             # Viewer-specific widgets/helpers
│       └── analytics_ui.py          # Analytics-specific widgets/helpers
│
├── config/
│   ├── dbconf.yaml
│   └── tickers.csv
│
├── sql/
│   └── create_tables.sql
│
├── requirements.txt                 # Updated with streamlit, plotly, pandas
├── requirements-cli.txt             # Original deps only (for CLI-only usage)
└── run_cli.sh                       # Convenience script for CLI mode
```

---

## Design Principles

1. **Strict separation**: `shared/` contains ALL business logic. `dashboard/` and `cli/` are thin consumers.
2. **No Streamlit imports in `shared/`**: The shared layer must never import `streamlit`, `plotly`, or any UI library. This ensures it can be reused with any frontend.
3. **No business logic in `dashboard/`**: Streamlit pages call into `shared/` functions and render results. No yfinance calls, no DB queries, no CSV manipulation in UI code.
4. **CLI parity**: The `cli/main.py` refactored to import from `shared/` must produce identical behaviour to the current `src/main.py`.
5. **Original functionality preserved**: Running `cli/main.py` works exactly as before.

---

## Step-by-Step Implementation

### Phase 1 — Extract shared business logic

**1.1 Create `shared/` package**

- Create `shared/__init__.py`
- Create `shared/config.py` — centralises path resolution (project root, config dir, src dir) so all modules resolve paths consistently regardless of entry point

**1.2 Move `db.py` → `shared/db.py`**

- Copy `data-ingestion-module/src/db.py` to `shared/db.py`
- Update `load_db_config()` to use `config.py` for path resolution
- All SQL constants and helpers remain unchanged

**1.3 Move `ingest.py` → `shared/ingest.py`**

- Copy `data-ingestion-module/src/ingest.py` to `shared/ingest.py`
- No logic changes — only adjust imports to reference `shared.db`

**1.4 Move `roster.py` → `shared/roster.py`**

- Copy `data-ingestion-module/src/roster.py` to `shared/roster.py`
- Update `ROSTER_PATH` to use `config.py` path resolution

**1.5 Move `logging_setup.py` → `shared/logging_setup.py`**

- Direct copy, no changes needed

**1.6 Create `shared/queries.py`** (new — for viewer/analytics)

This file contains read-only DB queries that don't exist yet. These are presentation-agnostic query functions that return plain Python dicts/lists/pandas DataFrames.

```python
# Functions to implement:

def get_all_tickers(conn) -> list[dict]
    """Return all tickers with metadata and sync status (JOIN tickers + ticker_sync)"""

def get_ticker_detail(conn, ticker: str) -> dict
    """Full metadata + sync status for one ticker"""

def get_candles(conn, ticker: str, start_date=None, end_date=None) -> list[dict]
    """Daily OHLCV for a ticker within optional date range"""

def get_candles_df(conn, ticker: str, start_date=None, end_date=None) -> pd.DataFrame
    """Same as get_candles but returns a pandas DataFrame (for analytics)"""

def get_dividends(conn, ticker: str) -> list[dict]
    """Dividend history for a ticker"""

def get_splits(conn, ticker: str) -> list[dict]
    """Split history for a ticker"""

def get_sync_summary(conn) -> dict
    """Aggregate stats: total tickers, last sync time, data range"""

def get_available_date_range(conn, ticker: str) -> tuple[date, date]
    """Min and max trade_date for a ticker"""

def get_tickers_with_stats(conn) -> list[dict]
    """Each ticker with candle count, dividend count, split count"""
```

All functions accept a `conn` parameter — no global DB state. Returns are plain dicts or DataFrames. No Streamlit, no Plotly, no UI logic.

---

### Phase 2 — Refactor CLI to use shared/

**2.1 Create `cli/main.py`**

- Import `shared.db`, `shared.ingest`, `shared.roster`, `shared.logging_setup`
- Port all CLI logic from `data-ingestion-module/src/main.py` — menu loop, `do_update()`, `do_add()`, `do_list()`, `timed_task()`, `is_tradable()`
- All business logic calls go through `shared/` functions
- Verify: running `cli/main.py` produces identical behaviour to current `src/main.py`

**2.2 Create `run_cli.sh`**

```bash
#!/usr/bin/env bash
cd "$(dirname "$0")"
python3 -m cli.main "$@"
```

**2.3 Keep `data-ingestion-module/` untouched**

- The original directory remains as-is for reference and backward compatibility
- It can be deprecated later but is not deleted or modified

---

### Phase 3 — Build Streamlit dashboard

**3.1 Create `dashboard/app.py`** (Streamlit entry point)

```python
import streamlit as st

st.set_page_config(page_title="R9 Analytics", layout="wide")
st.sidebar.title("R9 Analytics")

page = st.sidebar.radio(
    "Navigate",
    ["Data Ingestion", "Data Viewer", "Data Analytics"]
)

# Delegate to page modules
if page == "Data Ingestion":
    from dashboard.pages import ingestion_page
    ingestion_page.render()
elif page == "Data Viewer":
    from dashboard.pages import viewer_page
    viewer_page.render()
elif page == "Data Analytics":
    from dashboard.pages import analytics_page
    analytics_page.render()
```

**3.2 Create `dashboard/components/` helpers**

These are small Streamlit-specific utility functions (caching, formatting, layout helpers). They do NOT contain business logic — only UI composition.

```python
# components/ingestion_ui.py
def render_ticker_table(tickers: list[dict]) -> None
    """Render a st.dataframe showing ticker sync status"""

def render_sync_status(stats: dict) -> None
    """Show sync results in an st.success/st.error callout"""

def render_add_ticker_form() -> str | None
    """Form for adding a new ticker, returns symbol or None"""

# components/viewer_ui.py
def render_candle_chart(df: pd.DataFrame, ticker: str) -> None
    """Plotly candlestick chart using st.plotly_chart"""

def render_data_table(data: list[dict], title: str) -> None
    """Styled st.dataframe with title"""

def render_date_filter() -> tuple[date, date]
    """Date range selector widgets"""

# components/analytics_ui.py
def render_metric_cards(metrics: dict) -> None
    """Row of st.metric cards (price change, volume, etc.)"""

def render_distribution_chart(data, title: str) -> None
    """Plotly histogram/distribution chart"""

def render_correlation_matrix(df: pd.DataFrame) -> None
    """Plotly heatmap of correlations"""
```

**3.3 Create `dashboard/pages/1_Data_Ingestion.py`**

Streamlit page for ingestion operations. Calls into `shared/` for all logic.

Features:
- **Ticker roster view**: Table of all tickers with sync status (calls `shared.queries.get_tickers_with_stats()`)
- **Add ticker form**: Input field + button → calls `shared.ingest.sync_ticker()` via a wrapper
- **Update all tickers**: Button to trigger bulk sync → calls `shared.ingest.sync_ticker()` for each ticker
- **Sync status**: Show last sync time, data range, any errors
- **Progress bar**: During bulk sync, show progress with `st.progress()`

Important: The actual sync operations should be wrapped in thin functions in `shared/` that the UI calls. The UI should NOT directly call yfinance.

**3.4 Create `dashboard/pages/2_Data_Viewer.py`**

Streamlit page for browsing ingested data. Read-only.

Features:
- **Ticker selector**: Dropdown populated from `shared.queries.get_all_tickers()`
- **Candle data table**: Date-filtered OHLCV table via `shared.queries.get_candles()`
- **Candlestick chart**: Plotly candlestick via `dashboard/components/analytics_ui.py` or `viewer_ui.py`
- **Dividends table**: Via `shared.queries.get_dividends()`
- **Splits table**: Via `shared.queries.get_splits()`
- **Ticker metadata card**: Name, sector, industry, exchange etc.

**3.5 Create `dashboard/pages/3_Data_Analytics.py`**

Streamlit page for calculations and analytics. All computations happen in `shared/` or via pandas/plotly directly on data returned from `shared.queries`.

Features:
- **Multi-ticker comparison**: Select multiple tickers, overlay price charts
- **Performance metrics**: Returns over 1M/3M/6M/1Y/YTD, CAGR, max drawdown
- **Volume analysis**: Volume trends, average volume by ticker
- **Correlation matrix**: Cross-ticker correlation of daily returns
- **Dividend yield analysis**: For tickers with dividend data
- **Sector breakdown**: Pie/bar chart of portfolio by sector
- All charts use Plotly (`st.plotly_chart()`)

---

### Phase 4 — Dependencies and configuration

**4.1 Update `requirements.txt`**

```
psycopg>=3.3.5
pyyaml>=6.0.3
yfinance>=1.7.0
streamlit>=1.63.0
plotly>=7.0.0
pandas>=3.0.5
```

**4.2 Create `requirements-cli.txt`** (for CLI-only usage)

```
psycopg>=3.3.5
pyyaml>=6.0.3
yfinance>=1.7.0
```

**4.3 Create `run_dashboard.sh`**

```bash
#!/usr/bin/env bash
cd "$(dirname "$0")"
streamlit run dashboard/app.py
```

---

### Phase 5 — Verification

**5.1 CLI verification**

- Run `./run_cli.sh` and test all menu commands
- Verify output matches current `src/main.py` behaviour exactly

**5.2 Dashboard verification**

- Run `./run_dashboard.sh`
- Navigate to each page
- Verify Data Ingestion: can view roster, add ticker, trigger sync
- Verify Data Viewer: can select ticker, view candles/dividends/splits
- Verify Data Analytics: charts render, metrics calculate correctly

**5.3 Separation verification**

- `grep -r "import streamlit" shared/` → must return zero results
- `grep -r "import plotly" shared/` → must return zero results
- `grep -r "shared\." dashboard/` → should show all cross-boundary calls

---

## Migration Checklist

| # | Task | Status |
|---|------|--------|
| 1 | Create `shared/` package with `__init__.py`, `config.py` | [x] |
| 2 | Move `db.py` → `shared/db.py` | [x] |
| 3 | Move `ingest.py` → `shared/ingest.py` | [x] |
| 4 | Move `roster.py` → `shared/roster.py` | [x] |
| 5 | Move `logging_setup.py` → `shared/logging_setup.py` | [x] |
| 6 | Create `shared/queries.py` (read-only queries for viewer/analytics) | [x] |
| 7 | Create `cli/main.py` (refactored CLI importing from shared/) | [x] |
| 8 | Create `run_cli.sh` | [x] |
| 9 | Verify CLI behaviour matches original | [x] |
| 10 | Create `dashboard/app.py` (Streamlit entry point with sidebar nav) | [x] |
| 11 | Create `dashboard/components/` (ingestion_ui, viewer_ui, analytics_ui) | [x] |
| 12 | Create `dashboard/pages/ingestion_page.py` | [x] |
| 13 | Create `dashboard/pages/viewer_page.py` | [x] |
| 14 | Create `dashboard/pages/analytics_page.py` | [x] |
| 15 | Update `requirements.txt` with streamlit, plotly, pandas | [x] |
| 16 | Create `requirements-cli.txt` | [x] |
| 17 | Create `run_dashboard.sh` | [x] |
| 18 | Verify no UI imports in `shared/` | [x] |
| 19 | Verify dashboard renders all three pages | [x] |

---

## Future Stripping of Streamlit

When a proper UI is needed:
1. Delete `dashboard/` and `run_dashboard.sh`
2. Build new UI that imports from `shared/` (same way `dashboard/` does)
3. `shared/` is the stable API contract between backend and any frontend

No business logic changes required. The `shared/` layer is the permanent, reusable core.

---

## Notes

- The `data-ingestion-module/` directory is preserved untouched as a fallback
- All DB queries in `shared/queries.py` accept a `conn` parameter — no global state
- Streamlit's `st.cache_data` can be used in UI components for performance, but the underlying data always comes from `shared/` query functions
- Plotly is only imported in `dashboard/` — never in `shared/`
- The `shared/config.py` module centralises all path resolution so both CLI and dashboard find config files correctly regardless of working directory
