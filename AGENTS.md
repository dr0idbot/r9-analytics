# AGENTS.md — Implementation Instructions

> Read this before starting any implementation work on R9 Analytics.
> This file defines the rules, workflow, and verification steps for agents.

---

## Quick Reference

| Item | Value |
|------|-------|
| Project root | `/home/droidbot/project-source/r9-analytics` |
| Python version | 3.12+ |
| Entry points (after build) | `python -m cli.main` (CLI), `streamlit run dashboard/app.py` (dashboard) |
| Config dir | `config/` |
| Shared logic | `shared/` |
| Guidelines | `GUIDELINES.md` |

---

## Before You Start

1. **Read `GUIDELINES.md`** — it defines all rules, standards, and constraints.
2. **Read `shared/db.py`** — all SQL constants and DB connection logic.
3. **Read `shared/ingest.py`** — yfinance fetch and sync logic.
4. **Read `shared/queries.py`** — read-only queries for viewer/analytics.
5. **Read `cli/main.py`** — the CLI interface.

---

## Implementation Workflow

### For every task, follow this cycle:

```
PLAN → IMPLEMENT → VERIFY → LINT → COMMIT (only if asked)
```

### Step 1 — Plan

- Identify which files need to be created or modified.
- Identify which `shared/` functions the new code depends on.
- Check if the dependency already exists or needs to be created first.
- Update `plan/PLAN.md` checklist if a new subtask is discovered.

### Step 2 — Implement

- Write code following all rules in `GUIDELINES.md`.
- Start from the bottom of the dependency chain: `shared/config.py` → `shared/db.py` → `shared/ingest.py` → `shared/roster.py` → `shared/queries.py` → `cli/` → `dashboard/`.
- Do not skip ahead. Each layer depends on the one before it.

### Step 3 — Verify

- Run the module standalone to check for import errors:
  ```bash
  python -c "from shared import db, ingest, roster, queries; print('OK')"
  ```
- Run any existing tests:
  ```bash
  python -m pytest tests/ -v
  ```
- For CLI: run `python -m cli.main` and test menu commands.
- For dashboard: run `streamlit run dashboard/app.py` and navigate all pages.

### Step 4 — Lint

Run type checking and linting before considering a task complete:

```bash
# Type checking
python -m mypy shared/ cli/ dashboard/ --ignore-missing-imports

# Linting
python -m ruff check shared/ cli/ dashboard/

# Format check
python -m ruff format --check shared/ cli/ dashboard/
```

If these tools are not installed, install them first:

```bash
pip install mypy ruff
```

### Step 5 — Commit

Only commit when explicitly asked by the user. Follow commit message format from `GUIDELINES.md` §10.

---

## Dependency Chain (Build Order)

You must build in this exact order. Each step depends on the previous.

```
1. shared/__init__.py
2. shared/config.py          ← path resolution, env var support
3. shared/db.py              ← copy from src/db.py, update imports via config.py
4. shared/ingest.py          ← copy from src/ingest.py, update imports
5. shared/roster.py          ← copy from src/roster.py, update path via config.py
6. shared/logging_setup.py   ← direct copy, no changes
7. shared/queries.py         ← NEW: read-only queries for viewer/analytics
8. cli/__init__.py
9. cli/main.py               ← refactor from src/main.py, import from shared/
10. dashboard/__init__.py
11. dashboard/app.py         ← Streamlit entry point with sidebar nav
12. dashboard/components/    ← UI helper functions
13. dashboard/pages/         ← the three page files
14. requirements.txt         ← update with all deps at latest versions
15. requirements-cli.txt     ← original 3 deps only
16. run_cli.sh, run_dashboard.sh
```

---

## Critical Rules

### Never break the CLI

After every change to `shared/`, verify the CLI still works:

```bash
python -m cli.main
```

Test: `list`, `add AAPL` (or any known ticker), `update`, `exit`.

### Never put business logic in dashboard/

If you find yourself writing yfinance calls, DB queries, or CSV parsing inside a `dashboard/` file, stop. Move that logic to `shared/` and call it from there.

### Never import streamlit in shared/

If you accidentally add `import streamlit as st` to any file in `shared/`, the build is broken. Verify with:

```bash
grep -r "import streamlit" shared/
# Must return nothing
```

### Always use type hints

Every function must have full type annotations. If you see a function without them, add them.

### Always log

Every significant operation must be logged. The user should never wonder "did anything happen?" If a function takes more than 1 second or processes more than 1 row, log it.

### Always handle connection lifecycle

Use `with get_connection(config) as conn:` — never manual open/close/commit.

---

## Logging Requirements

When implementing, ensure every operation logs:

1. **Start**: What is about to happen
2. **Progress**: Per-item progress for loops (e.g. "Syncing ticker 5/113: MSFT")
3. **Result**: What happened — counts, elapsed time, success/failure
4. **Errors**: Full context — which ticker, which operation, what went wrong

Example for a sync operation:

```python
logger.info("Starting bulk sync for %d tickers", len(tickers))
for i, ticker in enumerate(tickers, 1):
    logger.info("Syncing ticker %d/%d: %s", i, len(tickers), ticker)
    try:
        stats = sync_ticker(conn, ticker, resume_from=last_date)
        logger.info("  %s: %d candles synced (through %s)",
                    ticker, stats["candles"], stats["last_candle_date"])
    except Exception as e:
        logger.error("  %s failed: %s", ticker, e)
        failures.append(ticker)
logger.info("Bulk sync complete: %d succeeded, %d failed in %.1fs",
            len(tickers) - len(failures), len(failures), elapsed)
```

For Streamlit, mirror log calls to user-facing widgets:

```python
logger.info("Syncing %s...", ticker)
st.info(f"Syncing {ticker}...")
# ... do work ...
logger.info("Sync complete for %s", ticker)
st.success(f"Sync complete for {ticker}")
```

---

## Verification Checklist

Before marking any task as done, confirm:

- [ ] `python -c "from shared import db, ingest, roster, queries"` works
- [ ] `grep -r "import streamlit" shared/` returns nothing
- [ ] `grep -r "import plotly" shared/` returns nothing
- [ ] All new functions have type hints
- [ ] All new functions have docstrings
- [ ] All significant operations are logged
- [ ] CLI commands work: `list`, `add`, `update`, `exit`
- [ ] Dashboard pages load without errors
- [ ] `ruff check` passes (or only has pre-existing warnings)
- [ ] No secrets in code (passwords from env vars or config only)

---

## If Something Goes Wrong

| Problem | Action |
|---------|--------|
| Import error in `shared/` | Check `shared/config.py` path resolution. Ensure `__init__.py` exists. |
| CLI crashes on startup | Check `PYTHONPATH` or `python -m` invocation. Ensure `shared/` is importable. |
| Dashboard can't find config | Check working directory. `dashboard/app.py` must resolve paths via `shared/config.py`. |
| yfinance returns empty data | Ticker may be delisted. Log warning, skip, continue. Do not crash. |
| DB connection fails | Log error with full context (host, port, dbname). Raise to caller. |
| Plotly chart won't render | Check DataFrame columns match expected schema. Log the DataFrame shape. |

---

## When You Finish

1. Run the full verification checklist above.
2. Update `plan/PLAN.md` — mark completed items with `[x]`.
3. Do NOT commit unless the user explicitly asks.
4. Report what you did, what works, and what remains.
