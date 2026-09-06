# Guidelines — R9 Analytics

> Rules, assumptions, and standards that govern all code in this project.
> Every contributor (human or agent) must follow these.

---

## 1. Architecture

### 1.1 Three-layer separation

```
shared/   →  Business logic (DB, fetch, queries, config)
cli/      →  CLI presentation (imports from shared/)
dashboard/ →  Streamlit presentation (imports from shared/)
```

**Immutable rule:** `shared/` must never import `streamlit`, `plotly`, `pandas` plotting, or any UI library. It returns plain dicts, lists, and DataFrames. The presentation layers consume them.

### 1.2 Original CLI preservation

`cli/main.py` must reproduce the exact behaviour of `data-ingestion-module/src/main.py`. No feature additions, no removed commands, no changed log messages. It is a refactor (import path changes only), not a rewrite.

### 1.3 `data-ingestion-module/` is frozen

The original directory is kept for reference and fallback. Do not modify files inside it.

---

## 2. Code Standards

### 2.1 Python version

Target **Python 3.12+**. Use modern syntax:
- `dict | None` union types (not `Optional[dict]`)
- `from __future__ import annotations` at top of every module
- f-strings only (no `.format()`, no `%`)

### 2.2 Type hints

Every function must have complete type hints — arguments and return type. No exceptions.

```python
# GOOD
def get_candles(conn: Connection, ticker: str, start: date | None = None) -> list[dict]:
    ...

# BAD
def get_candles(conn, ticker, start=None):
    ...
```

### 2.3 Imports

- Standard library first, then third-party, then local — separated by blank lines.
- Use `from __future__ import annotations` as the very first import.
- No wildcard imports (`from x import *`).

### 2.4 Naming

| Element | Convention | Example |
|---------|-----------|---------|
| Files/modules | `snake_case.py` | `ingest.py`, `data_viewer.py` |
| Functions | `snake_case()` | `fetch_candles()`, `get_all_tickers()` |
| Classes | `PascalCase` | `ColorFormatter` |
| Constants | `UPPER_SNAKE` | `Q_UPSERT_CANDLE`, `ROSTER_PATH` |
| Streamlit pages | `N_Title_Case.py` | `1_Data_Ingestion.py` |
| Streamlit page vars | `snake_case` | `ingestion_page.py` |

### 2.5 Docstrings

Every public function and module must have a docstring. Use Google style:

```python
def sync_ticker(conn: Connection, symbol: str, force_full: bool = False) -> dict:
    """Fetch and upsert all data for a single ticker.

    Args:
        conn: Active database connection.
        symbol: Yahoo Finance ticker symbol.
        force_full: If True, ignore resume point and fetch full history.

    Returns:
        Dict with keys: ticker, candles, dividends, splits, from, last_candle_date.

    Raises:
        RuntimeError: If ticker is unavailable or has zero data.
    """
```

Internal/private helpers (`_prefix`) do not require docstrings but should have a one-line comment explaining purpose.

### 2.6 Error handling

- **`shared/` layer:** Raise exceptions. Do not catch and swallow errors. Let the caller decide how to handle them.
- **Presentation layers (`cli/`, `dashboard/`):** Catch exceptions from `shared/` and present them to the user (log for CLI, `st.error()` for Streamlit).
- Never use bare `except:` or `except Exception:` without re-raising or logging.

### 2.7 No magic numbers

All magic numbers must be named constants. Example:

```python
# BAD
if len(data) > 100:
    ...

# GOOD
MAX_BATCH_SIZE = 100
if len(data) > MAX_BATCH_SIZE:
    ...
```

---

## 3. Database

### 3.1 SQL constants

All SQL queries are defined as **module-level constants** in `shared/db.py`. No queries are built at runtime. Prefix with `Q_`.

```python
Q_GET_CANDLES = """
    SELECT trade_date, open, high, low, close, adj_close, volume
    FROM market.daily_candles
    WHERE ticker = %s
    ORDER BY trade_date
"""
```

### 3.2 Connection management

`get_connection()` is a context manager. All callers use `with`:

```python
with get_connection(config) as conn:
    result = conn.execute(Q_SOME_QUERY, (param,))
```

No manual commit/rollback/close.

### 3.3 Schema

All tables live in the `market` schema. SQL constants must always reference `market.tablename`. Do not rely on `search_path`.

### 3.4 Idempotency

All writes use `ON CONFLICT ... DO UPDATE`. Re-running any operation must be safe.

---

## 4. Configuration

### 4.1 Path resolution

All path resolution goes through `shared/config.py`. No module computes its own `Path(__file__).parent.parent` chains. This ensures paths work regardless of working directory or entry point.

### 4.2 Config files

- `config/dbconf.yaml` — DB connection. Password may be overridden by env var `R9_DB_PASSWORD`.
- `config/tickers.csv` — Authoritative ticker roster. Only modified by `shared/roster.py` functions.

### 4.3 Secrets

Never log, print, or expose database passwords. In `shared/` code, read password from env var first, fall back to config file only.

```python
password = os.environ.get("R9_DB_PASSWORD") or yaml_config.get("password")
```

---

## 5. Dependencies

All dependencies must be pinned to **latest stable versions** as of project setup. Updated in `requirements.txt` at root.

| Package | Latest | Purpose |
|---------|--------|---------|
| `psycopg` | `>=3.3.5` | PostgreSQL adapter (v3) |
| `pyyaml` | `>=6.0.3` | YAML config parsing |
| `yfinance` | `>=1.7.0` | Yahoo Finance data API |
| `streamlit` | `>=1.63.0` | Web dashboard framework |
| `plotly` | `>=7.0.0` | Interactive charts |
| `pandas` | `>=3.0.5` | DataFrames for analytics |

**Rules:**
- Never add a dependency without documenting it here and in `requirements.txt`.
- Check for conflicts before adding. Run `pip check` after install.
- `requirements-cli.txt` contains only the original 3 deps (psycopg, pyyaml, yfinance) for CLI-only usage.
- Do not use libraries that duplicate functionality already provided by an existing dependency (e.g. do not add `requests` — `yfinance` already uses it internally).

---

## 6. Logging

### 6.1 Standard

Every module uses Python's `logging` module. No `print()` for operational output.

```python
import logging
logger = logging.getLogger(__name__)
```

### 6.2 Levels

| Level | When to use |
|-------|------------|
| `DEBUG` | Detailed diagnostic info — raw API responses, SQL params, path resolution |
| `INFO` | Operational milestones — "Sync started", "50 tickers updated", "Dashboard running on port 8501" |
| `WARNING` | Recoverable issues — rate limit hit, ticker delisted, fallback to cached data |
| `ERROR` | Failures — DB connection lost, yfinance API error, file not found |

### 6.3 Context

Every log message must include enough context to understand what happened without reading the surrounding code:

```python
# BAD
logger.info("Sync complete")

# GOOD
logger.info("Sync complete for %s: %d candles, %d dividends, %d splits in %.1fs",
            symbol, stats["candles"], stats["dividends"], stats["splits"], elapsed)
```

### 6.4 Dashboard logging

In Streamlit pages, log to Python logger AND display to user via `st.info()` / `st.warning()` / `st.error()` as appropriate. The logger is for server-side debugging; Streamlit widgets are for the user.

### 6.5 Coloured CLI output

`shared/logging_setup.py` provides coloured output for the CLI. The dashboard does not use it (Streamlit has its own UI for status).

---

## 7. Streamlit-Specific

### 7.1 Page structure

- `dashboard/app.py` is the entry point. It sets page config and provides sidebar navigation.
- Each page is a separate file in `dashboard/pages/` with a `render()` function.
- Page files are named `N_Title_Case.py` where N is the display order.

### 7.2 Caching

Use `st.cache_data` with appropriate `ttl` for expensive queries:

```python
@st.cache_data(ttl=300)  # 5 minutes
def load_tickers():
    with get_connection(config) as conn:
        return get_all_tickers(conn)
```

Never cache write operations.

### 7.3 State

- Use `st.session_state` only for UI state (selected tab, filter values).
- Never store business data in session state — always fetch fresh from DB.
- On refresh, data is always re-fetched (no stale state from cache).

### 7.4 Forms

Use `st.form()` for multi-field inputs (add ticker, date range selection). Submit buttons inside forms prevent accidental re-runs.

### 7.5 Progress

For long operations (bulk sync), use `st.progress()` and `st.status()`:

```python
with st.status("Syncing tickers...", expanded=True) as status:
    for i, ticker in enumerate(tickers):
        st.write(f"Syncing {ticker}...")
        # ... do work ...
        progress.progress((i + 1) / len(tickers))
    status.update(label="Sync complete", state="complete")
```

### 7.6 Charts

All charts use Plotly via `st.plotly_chart()`. Chart-building functions live in `dashboard/components/` and accept DataFrames/dicts. They return nothing — they call `st.plotly_chart()` directly.

---

## 8. Testing

### 8.1 Framework

Use `pytest` for all tests. Tests live in a top-level `tests/` directory.

```
tests/
├── test_shared/
│   ├── test_db.py
│   ├── test_ingest.py
│   ├── test_roster.py
│   └── test_queries.py
└── test_cli/
    └── test_main.py
```

### 8.2 Coverage targets

- `shared/` layer: minimum 80% line coverage.
- `cli/` and `dashboard/`: tested via integration/smoke tests, not unit tests (they are thin wrappers).

### 8.3 Test data

Tests use a test database (`r9_analytics_test`) or mocked connections. Never run tests against the production database.

---

## 9. File Layout Rules

- **No nested `src/` directories** in the new structure. `shared/`, `cli/`, `dashboard/` are top-level packages.
- **No business logic in `dashboard/components/`** — these are purely UI composition helpers.
- **One class per file** is preferred. Small utility modules (under 50 lines) may contain related helpers.
- **`__init__.py` files** must exist in every package directory. They can be empty or contain `__all__` exports.

---

## 10. Version Control

- Commit messages: `<type>: <description>` (e.g. `feat: add data viewer page`, `fix: resolve connection timeout`)
- Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`
- Never commit: `config/dbconf.yaml` with real passwords, `__pycache__/`, `.env` files

---

## 11. Known Constraints

1. yfinance has no official API and may break without notice. Pin `yfinance>=1.7.0` and test after upgrades.
2. yfinance rate-limits aggressively for bulk fetches. The current codebase has no retry/backoff — this is a known limitation.
3. The `tickers.csv` roster is single-writer (one CLI or one dashboard instance). Concurrent writes will corrupt it.
4. PostgreSQL connection uses `psycopg` v3 (not v2). Do not use v2 API patterns.

---

## 12. Future Work (not in scope now)

- Rate-limit/retry handling for yfinance
- `remove` command for dropping tickers
- Environment-variable-based config (12-factor)
- Concurrent write safety for tickers.csv (file lock or DB-only roster)
- Scheduled ingestion (cron / APScheduler)
