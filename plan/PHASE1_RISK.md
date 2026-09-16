# Phase 1 — Single-Asset Risk Metrics

## Overview

Implement per-ticker risk calculations using daily OHLCV data. All metrics are computed from existing candle data — no new data fetching.

---

## Step 1.1 — Foundation: Daily Returns

Create helper function to compute daily returns from close prices.

**File:** `shared/calculations.py`

**Function:**
```python
def daily_returns(conn, ticker, start_date=None, end_date=None) -> pd.Series:
    """Compute daily simple returns from close prices."""
    # Use get_candles_df() to get close prices
    # Return pct_change().dropna()
```

**Dependencies:** `shared.queries.get_candles_df()`

**Test:** Verify returns for AAPL are between -1.0 and +1.0, no NaN after dropna.

---

## Step 1.2 — Realized Volatility

Annualized standard deviation of daily returns.

**Function:**
```python
def realized_volatility(conn, ticker, window=None, annualize=True) -> float:
    """Compute realized volatility.
    
    Args:
        window: If None, use all data. If int, use rolling window.
        annualize: If True, multiply by sqrt(252).
    """
```

**Formula:** `std(returns) × √252`

**Test:** Volatility should be positive. AAPL historical vol typically 20-40%.

---

## Step 1.3 — Value at Risk (VaR)

Maximum expected loss at a confidence level.

**Functions:**
```python
def historical_var(conn, ticker, confidence=0.95, horizon=1) -> float:
    """Historical VaR — empirical percentile of returns.
    
    Returns the loss threshold (negative number).
    e.g., -0.03 means 95% chance of losing no more than 3%.
    """

def parametric_var(conn, ticker, confidence=0.95, horizon=1) -> float:
    """Parametric VaR — assumes normal distribution.
    
    Formula: mean + z_score × std
    """
```

**Test:** |VaR| should be reasonable (typically 1-5% for daily 95% VaR).

---

## Step 1.4 — Conditional VaR (CVaR)

Average loss beyond VaR threshold.

**Function:**
```python
def cvar(conn, ticker, confidence=0.95) -> float:
    """Conditional VaR (Expected Shortfall).
    
    Mean of all returns that are worse than VaR.
    Always worse (more negative) than VaR.
    """
```

**Formula:** `mean(returns[returns <= VaR])`

**Test:** CVaR should be worse (more negative) than VaR.

---

## Step 1.5 — Parkinson Volatility

Volatility using high/low prices (more accurate than close-only).

**Function:**
```python
def parkinson_volatility(conn, ticker, annualize=True) -> float:
    """Parkinson volatility estimator using high/low range.
    
    Formula: sqrt(1/(4n×ln2) × Σ(ln(high/low))²)
    """
```

**Dependencies:** Needs high and low columns from candles.

**Test:** Should be close to realized volatility but typically slightly lower.

---

## Step 1.6 — Garman-Klass Volatility

Most efficient OHLC-based volatility estimator.

**Function:**
```python
def garman_klass_volatility(conn, ticker, annualize=True) -> float:
    """Garman-Klass volatility using OHLC data.
    
    Formula: sqrt(0.5×ln(H/L)² - (2ln2-1)×ln(C/O)²)
    """
```

**Test:** Should be more efficient (lower variance) than Parkinson.

---

## Step 1.7 — Maximum Drawdown

Worst peak-to-trough decline.

**Function:**
```python
def max_drawdown(conn, ticker) -> float:
    """Maximum drawdown from peak.
    
    Returns negative number (e.g., -0.35 for 35% drawdown).
    """
```

**Formula:** `min((price - cummax) / cummax)`

**Test:** Should be negative. Magnitude depends on ticker history.

---

## Step 1.8 — Semi-Deviation

Standard deviation of negative returns only.

**Function:**
```python
def semi_deviation(conn, ticker, annualize=True) -> float:
    """Downside volatility — only negative returns.
    
    Only considers returns below 0 (or below risk-free rate).
    """
```

**Test:** Should be less than or equal to total volatility.

---

## Step 1.9 — Downside Ratio

Proportion of total risk that is downside.

**Function:**
```python
def downside_ratio(conn, ticker) -> float:
    """Ratio of semi-deviation to total volatility.
    
    Returns value between 0 and 1.
    Higher = more downside risk relative to total risk.
    """
```

**Formula:** `semi_deviation / realized_volatility`

**Test:** Value between 0 and 1.

---

## Step 1.10 — Aggregate Function

Single entry point to compute all Phase 1 metrics.

**Function:**
```python
def single_asset_risk(conn, ticker) -> dict:
    """Compute all single-asset risk metrics for a ticker.
    
    Returns dict with:
        realized_volatility, historical_var, parametric_var,
        cvar, parkinson_volatility, garman_klass_volatility,
        max_drawdown, semi_deviation, downside_ratio
    """
```

---

## Database Changes

None. All calculations use existing candle data.

---

## Files Modified

| File | Changes |
|------|---------|
| `shared/calculations.py` | Add all Phase 1 functions |

---

## Verification

1. Compute metrics for AAPL, MSFT, TSLA — verify reasonable values
2. Verify VaR < 0 (losses are negative)
3. Verify CVaR < VaR (worse than VaR)
4. Verify volatility > 0
5. Verify max_drawdown < 0
6. Verify 0 <= downside_ratio <= 1
