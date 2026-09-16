# Version History — R9 Analytics

Clean implementation log for all released versions.

---

## v1.0.0 — Initial Release

**Tag:** `v1.0.0`
**Commits:** `8da8ac1` → `95030cf`

### What was built
- Streamlit dashboard with 4 pages: Data Ingestion, Data Viewer, Data Analytics, Theme
- `shared/` package with DB layer, ingestion, queries, config
- `cli/` interface with basic commands: `list`, `add`, `update`, `exit`
- Catppuccin Latte/Mocha theme with dark mode toggle
- Zebra striping and right-aligned numeric columns in DataFrames

### Key files
- `shared/db.py` — PostgreSQL connection, SQL constants
- `shared/ingest.py` — yfinance fetch and sync
- `shared/queries.py` — read-only queries
- `dashboard/app.py` — Streamlit entry point
- `cli/main.py` — CLI interface

---

## v1.1.0 — Portfolio Management + Risk Metrics Phase 1

**Tag:** `v1.1.0`
**Commits:** `e55fd03` → `5b45663`

### What was built
- Portfolio CRUD: create, add/remove securities, delete
- Currency validation (securities must match portfolio currency)
- Portfolio exposure calculations (sector/industry breakdown)
- Risk Metrics Phase 1: VaR, CVaR, volatility, drawdown, semi-deviation
- CLI commands: `prisk`, `pl`, `pn`, `pa`, `pr`, `pd`, `px`
- Dashboard pages: Portfolio Manager, Portfolio Exposure, Portfolio Risk

### Database changes
- `market.portfolios` table
- `market.portfolio_securities` table
- `calc.risk_metrics` table

### Key files
- `shared/portfolio.py` — portfolio CRUD
- `shared/calculations.py` — risk calculations
- `dashboard/pages/portfolio_*.py` — portfolio pages

---

## v1.2.0 — Risk Metrics Phase 2–3 + Scenario Analysis

**Tag:** `v1.2.0`
**Commits:** `5157997` → `5c43195`

### What was built
- Risk Phase 2: Sharpe, Sortino, Calmar, Treynor, Information Ratio, Omega
- Risk Phase 3: Beta, Alpha, R-Squared, Tracking Error (vs SPY benchmark)
- Risk Phase 4: Portfolio-level risk (VaR, CVaR, Beta, Volatility, Diversification)
- Risk Phase 5: Scenario Analysis (historical stress test, drawdown duration, win rate)
- Dashboard pages: Risk Analysis, Scenario Analysis

### Key additions
- `beta()`, `tracking_error()`, `information_ratio()` functions
- `portfolio_risk()` function for portfolio-level aggregation
- `scenario_analysis()` function for stress testing
- Historical crisis returns (2008, 2020, etc.)

---

## v1.2.1 — Bug Fixes

**Tag:** `v1.2.1`
**Commits:** `2c69767` → `4864785`

### Fixes
- Import fixes: `list_portfolios` from `shared.portfolio`, `get_all_tickers` from `shared.queries`
- Context manager for all `get_connection()` calls
- `.get()` for risk metric keys to prevent KeyError
- Crisis return column format in scenario table
- Double `st.dataframe()` call removed

---

## v1.4.0 — Quantitative Foundation v2

**Tag:** `v1.4.0`
**Commits:** `cbd72e4` → `7b3cab2`

### What was built
- `shared/models/` — AnalysisContext, MetricResult dataclasses
- `shared/analytics/` — canonical return engine, portfolio, NAV, volatility, risk, performance, drawdown, missing data, dashboard helpers
- 217 unit tests across 12 test files
- `docs/METHODOLOGY.md` — quantitative methodology documentation
- `pyproject.toml` — editable install support

### Quantitative corrections
- VaR horizon: true multi-period returns (not sqrt scaling)
- Diversification ratio: removed /100 bug
- Drawdown: separated time_to_trough, recovery_time, total_duration
- Sharpe/Sortino: periodic excess returns with configurable rf
- Portfolio weight/data alignment with renormalization

### Key files
- `shared/analytics/returns.py` — canonical return engine
- `shared/analytics/portfolio.py` — market-value weighting
- `shared/analytics/volatility.py` — Parkinson, Garman-Klass
- `shared/analytics/risk.py` — VaR, CVaR
- `shared/analytics/performance.py` — Sharpe, Sortino, beta, alpha

---

## v1.5.0 — Portfolio Data Update

**Tag:** `v1.5.0`

### What was done
- Updated all portfolio buy prices to actual yfinance closing prices
- Created 4 new portfolios:
  - International Developed (id=14): SAP, ASML, NVO, SHEL, SONY, TSM, BABA, UL, NMR
  - Emerging Markets (id=15): PDD, BIDU, NIO, VALE, PBR, EWZ, EEM, FXI, KWEB, EZA
  - Crypto & Growth (id=16): COIN, MSTR, RIOT, MARA, BITO, ROKU, SNOW, DDOG, NET, CRWD
  - Fixed Income & Yield (id=17): BND, AGG, TLT, SCHD, VYM, O, AMT, PLD, NEE, DUK
- Removed PORT-1 (id=6)
- Synced 39 new tickers with full historical data

### Final state
- 8 portfolios, 89 securities
- Total: 154 securities across US, India, International, EM, Crypto, Fixed Income

---

## v1.5.1 — Security Boundary Documentation

**Tag:** `v1.5.1`
**Commit:** `f40c031`

### What was done
- Added section 13 "Security Boundary" to `GUIDELINES.md`
- Documented deployment model: localhost/trusted-network only
- Listed authentication options: streamlit-authenticator, oauth2-proxy, VPN
- Added exception message policy: safe messages to users, log server-side
- Added security warning banner in dashboard sidebar

---

## v1.5.2 — Sanitize Exception Messages

**Tag:** `v1.5.2`
**Commit:** `086154e`

### What was done
- Replaced all `str(e)` exposure in 8 dashboard pages with safe user messages
- Added `logger.exception()` for full server-side logging
- Added try/except to unprotected database calls
- Pages fixed: ingestion, viewer, analytics, portfolio_manager, portfolio_exposure, portfolio_risk, risk_analysis, scenario_analysis

---

## v1.5.3 — Validate Buy Date

**Tag:** `v1.5.3`
**Commit:** `7004c22`

### What was done
- Added `PortfolioError` when `buy_date > date.today()` in `shared/portfolio.py`
- Added validation tests for date constraints

---

## v1.5.4 — Redact Database Topology

**Tag:** `v1.5.4`
**Commit:** `b0b7e54`

### What was done
- Replaced detailed connection string logging (`user@host:port/dbname`) with generic message
- Database details only visible at TRACE level if needed for debugging

---

## Version Summary

| Version | Type | Description |
|---------|------|-------------|
| v1.0.0 | minor | Initial release — dashboard, CLI, shared layer |
| v1.1.0 | minor | Portfolio management + Risk Phase 1 |
| v1.2.0 | minor | Risk Phase 2–5 + Scenario Analysis |
| v1.2.1 | patch | Bug fixes (imports, context managers, formats) |
| v1.4.0 | minor | Quantitative Foundation v2 (analytics engine) |
| v1.5.0 | minor | Portfolio data update + 4 new portfolios |
| v1.5.1 | patch | Security boundary documentation |
| v1.5.2 | patch | Sanitize exception messages |
| v1.5.3 | patch | Validate buy_date not in future |
| v1.5.4 | patch | Redact database topology from logs |

---

## Next Planned Versions

| Version | Focus | Status |
|---------|-------|--------|
| v1.6.0 | Typed exceptions from yfinance fetch | Planned |
| v1.6.1 | Fix incremental sync success-after-failure | Planned |
| v1.6.2 | Eliminate CSV roster — PostgreSQL single source of truth | Planned |
| v1.6.3 | Fix dashboard bulk sync sync markers | Planned |
| v1.7.0 | Add current market value to portfolio | Planned |
| v1.7.1 | Use market-value weights for risk calculations | Planned |
| v1.7.2 | Batch data loading for risk calculations | Planned |
| v1.7.3 | Fix Sortino target semantics | Planned |
