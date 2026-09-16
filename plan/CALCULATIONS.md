# Risk Calculations — Implementation Plan

## Data Requirements

All calculations use existing data:
- Daily OHLCV candles (close, high, low, volume)
- Dividends (for total return adjustments)
- Portfolio holdings (buy_price, units, weights)

No new data fetching required.

---

## Phase 1 — Single-Asset Risk Metrics ✅ DONE

Per-ticker risk calculations using daily returns.

| Calculation | Formula | Purpose | Status |
|-------------|---------|---------|--------|
| **Value at Risk (VaR)** | Historical: sorted returns, percentile. Parametric: μ - z×σ | Maximum expected loss at confidence level (95%, 99%) | ✅ |
| **Conditional VaR (CVaR)** | Mean of returns below VaR | Average loss when loss exceeds VaR | ✅ |
| **Realized Volatility** | Std dev of returns × √252 | Annualized price fluctuation | ✅ |
| **Parkinson Volatility** | √(1/(4n×ln2) × Σ(ln(high/low))²) | Volatility using high/low (more accurate than close-only) | ✅ |
| **Garman-Klass Volatility** | Weighted combination of OHLC ranges | Most efficient OHLC-based volatility estimator | ✅ |
| **Maximum Drawdown** | Max peak-to-trough decline | Worst-case loss from peak | ✅ |
| **Semi-Deviation** | Std dev of negative returns only | Downside volatility | ✅ |
| **Downside Ratio** | Semi-deviation / total volatility | Proportion of risk that is downside | ✅ |

**File:** `shared/calculations.py`
**Schema:** `calc.risk_metrics` (Phase 1 columns)

---

## Phase 2 — Risk-Adjusted Return Metrics ✅ DONE

Per-ticker return quality metrics.

| Calculation | Formula | Purpose | Status |
|-------------|---------|---------|--------|
| **Sharpe Ratio** | (Return - Rf) / Volatility | Risk-adjusted return (needs risk-free rate) | ✅ |
| **Sortino Ratio** | (Return - Rf) / Downside Deviation | Return per unit of downside risk | ✅ |
| **Calmar Ratio** | Annualized Return / Max Drawdown | Return per unit of drawdown risk | ✅ |
| **Treynor Ratio** | (Return - Rf) / Beta | Return per unit of market risk | ✅ |
| **Information Ratio** | (Portfolio Return - Benchmark Return) / Tracking Error | Active management skill | ✅ |
| **Omega Ratio** | Sum(gains above threshold) / Sum(losses below threshold) | Probability-weighted gain/loss ratio | ✅ |

**Additional helpers:** `beta()`, `tracking_error()`, `_annualized_return()`
**Schema:** `calc.risk_metrics` (Phase 2 columns added)
**CLI:** `risk` command updated with Phase 2 section
**Dashboard:** Risk Analysis page updated with Phase 2 cards and detailed table

---

## Phase 3 — Market Risk Metrics ✅ DONE

Risk metrics requiring market/benchmark data (use SPY or index).

| Calculation | Formula | Purpose | Status |
|-------------|---------|---------|--------|
| **Beta** | Covariance(stock, market) / Variance(market) | Sensitivity to market movements | ✅ |
| **Alpha** | Portfolio Return - (Rf + Beta × (Market Return - Rf)) | Excess return beyond market compensation | ✅ |
| **R-Squared** | Correlation(stock, market)² | How much movement is explained by market | ✅ |
| **Tracking Error** | Std dev of (portfolio return - benchmark return) | Deviation from benchmark | ✅ |
| **Correlation Matrix** | Cross-ticker correlation of returns | Diversification benefit | ✅ (via beta/correlation helpers) |

**File:** `shared/calculations.py`
**Schema:** `calc.risk_metrics` (Phase 3 columns added)
**CLI:** `risk` command updated with Phase 3 section
**Dashboard:** Risk Analysis page updated with Market Risk section
**Note:** SPY fetched as benchmark ticker

---

## Phase 4 — Portfolio Risk Metrics ✅ DONE

Portfolio-level risk aggregation.

| Calculation | Formula | Purpose | Status |
|-------------|---------|---------|--------|
| **Portfolio VaR** | Weighted sum or simulation-based | Portfolio-level maximum loss | ✅ |
| **Portfolio CVaR** | Mean of portfolio losses beyond VaR | Expected loss in tail scenarios | ✅ |
| **Portfolio Beta** | Weighted sum of individual betas | Portfolio market sensitivity | ✅ |
| **Portfolio Volatility** | √(w' × Covariance × w) | Portfolio-level risk | ✅ |
| **Diversification Ratio** | (Σ w_i × σ_i) / σ_portfolio | Benefit from diversification | ✅ |
| **Concentration Index** | Herfindahl index of weights | Portfolio concentration risk | ✅ |
| **Value Contribution** | Weight × (Return - Rf) | Per-holding contribution to excess return | ✅ |

**File:** `shared/calculations.py`
**Schema:** `calc.portfolio_risk` (new table)
**CLI:** `prisk` command added
**Dashboard:** Portfolio Risk page added

---

## Phase 5 — Scenario Analysis ✅ DONE

Stress testing and scenario-based risk.

| Calculation | Description | Purpose | Status |
|-------------|-------------|---------|--------|
| **Historical Stress Test** | Apply past crisis returns to current portfolio | What if 2008/2020 happens again | ✅ |
| **Drawdown Duration** | Time from peak to recovery | How long capital is locked | ✅ |
| **Recovery Time** | Days from max drawdown to recovery | Liquidity risk assessment | ✅ |
| **Win Rate** | % of positive return periods | Consistency measure | ✅ |
| **Profit Factor** | Gross gains / Gross losses | Magnitude of wins vs losses | ✅ |

**File:** `shared/calculations.py`
**CLI:** `scenario` command added
**Dashboard:** Scenario Analysis page added

---

## Risk-Free Rate

For Sharpe/Sortino/Treynor calculations, use a configurable risk-free rate:
- Default: current T-bill rate (can be hardcoded or from config)
- Store in `config/dbconf.yaml` or as constant in `calculations.py`

---

## Implementation Order

| Phase | Effort | Dependencies |
|-------|--------|--------------|
| 1. Single-Asset Risk | Low | None |
| 2. Risk-Adjusted Return | Low | Phase 1 (volatility, drawdown) |
| 3. Market Risk | Medium | Need benchmark ticker (SPY) |
| 4. Portfolio Risk | Medium | Phase 1-3 + portfolio holdings |
| 5. Scenario Analysis | Medium | Phase 1 (drawdown) |

**Start with Phase 1** — foundational metrics used by all other phases.
