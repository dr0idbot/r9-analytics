# Implementation Plan — Pending Work

Current version: **v1.5.4**

---

## v1.6.0 — Typed Exceptions from yfinance

**Type:** minor

### Problem
External API failures are collapsed into empty datasets. Callers cannot distinguish "no data" from "fetch failed" from "rate limited".

### Fix
- Define `FetchError`, `RateLimitError`, `TickerNotFoundError` in `shared/ingest.py`
- Let `fetch_candles`, `fetch_dividends`, `fetch_splits` raise instead of returning `[]`
- Handle at presentation layer (CLI/Dashboard) with safe messages

### Files
- `shared/ingest.py`
- `dashboard/pages/ingestion_page.py`
- `cli/main.py`

---

## v1.6.1 — Fix Incremental Sync Success-After-Failure

**Type:** patch

### Problem
Incremental sync can record success after API/network failure. Database says "synced today" when no data was retrieved.

### Fix
- After fetching, validate at least one of (candles, dividends, splits) is non-empty for incremental sync
- Add `is_empty_response()` helper to distinguish "no data" from "fetch failed"
- Raise `SyncFailedError` when all empty and no explicit "no data" signal

### Files
- `shared/ingest.py`
- `tests/unit/test_ingest.py`

---

## v1.6.2 — Eliminate CSV Roster

**Type:** minor

### Problem
CSV roster and PostgreSQL create two competing sources of truth for ticker state.

### Fix
- Remove `shared/roster.py`
- Replace `read_roster()`/`write_roster()` with SQL queries against `market.tickers` + `market.ticker_sync`
- Update CLI `list`/`add` commands
- Update dashboard ingestion page

### Files
- `shared/roster.py` (delete)
- `shared/ingest.py`
- `cli/main.py`
- `dashboard/pages/ingestion_page.py`

---

## v1.6.3 — Fix Dashboard Bulk Sync Markers

**Type:** patch

### Problem
Dashboard sync doesn't update sync markers, causing stale state and repeated ingestion.

### Fix
- After dashboard bulk sync, call `upsert_sync()` for each ticker
- Use `max_candle_date()` from DB as resume point instead of CSV

### Files
- `dashboard/pages/ingestion_page.py`
- `shared/ingest.py`

---

## v1.7.0 — Add Current Market Value to Portfolio

**Type:** minor

### Problem
Portfolio "market value" is actually cost basis. UI labels imply current valuation.

### Fix
- Add `get_current_price(conn, ticker)` to `shared/queries.py`
- Add `market_value` and `current_price` fields to portfolio detail
- Keep `cost_basis` as separate field
- Update dashboard portfolio pages to show both

### Files
- `shared/queries.py`
- `shared/portfolio.py`
- `dashboard/pages/portfolio_manager_page.py`
- `dashboard/pages/portfolio_exposure_page.py`

---

## v1.7.1 — Use Market-Value Weights for Risk

**Type:** patch

### Problem
Portfolio risk uses cost-basis weights instead of current market-value weights.

### Fix
- Add `get_portfolio_weights(conn, portfolio_id, method="market_value"|"cost_basis")` helper
- Update `single_asset_risk`, `portfolio_var`, etc. to accept weights dict
- Default to market-value weights

### Files
- `shared/calculations.py`
- `shared/portfolio.py`

---

## v1.7.2 — Batch Data Loading for Risk Calculations

**Type:** patch

### Problem
Risk calculations repeatedly retrieve identical data from DB.

### Fix
- Add `load_portfolio_data(conn, portfolio_id) -> PortfolioData` that loads all prices/benchmark once
- Pass data structures to pure calculation functions
- Update all portfolio risk functions to accept pre-loaded data

### Files
- `shared/calculations.py`

---

## v1.7.3 — Fix Sortino Target Semantics

**Type:** patch

### Problem
Sortino implementation doesn't match documented target return semantics.

### Fix
- Review and correct Sortino ratio calculation to properly use target return (not rf_daily)
- Update docstring and methodology docs

### Files
- `shared/calculations.py`
- `docs/METHODOLOGY.md`
