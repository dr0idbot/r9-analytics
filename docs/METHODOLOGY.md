# Quantitative Methodology

This document describes the mathematical formulas, assumptions, and data requirements for all quantitative calculations in R9 Analytics.

## Table of Contents

1. [Returns](#1-returns)
2. [Volatility](#2-volatility)
3. [Risk-Adjusted Returns](#3-risk-adjusted-returns)
4. [Value at Risk](#4-value-at-risk)
5. [Performance Attribution](#5-performance-attribution)
6. [Drawdown Analysis](#6-drawdown-analysis)
7. [Portfolio Calculations](#7-portfolio-calculations)

---

## 1. Returns

### Simple Returns

$$r_t = \frac{P_t - P_{t-1}}{P_{t-1}}$$

- **Source**: Unadjusted prices
- **Use**: Cost-basis returns, dividend-adjusted returns
- **Minimum observations**: 2

### Total Returns (Adjusted)

$$r_t = \frac{P_t^{adj} - P_{t-1}^{adj}}{P_{t-1}^{adj}}$$

- **Source**: Dividend/split-adjusted prices
- **Use**: Performance measurement (recommended)
- **Minimum observations**: 2

### Log Returns

$$r_t = \ln\left(\frac{P_t}{P_{t-1}}\right)$$

- **Properties**: Time-additive, symmetric
- **Use**: Compounding, volatility estimation
- **Minimum observations**: 2

### Annualized Return

$$R_{ann} = \left(\prod_{t=1}^{T}(1+r_t)\right)^{N/T} - 1$$

- **N**: Periods per year (252 for daily)
- **T**: Number of return observations
- **Method**: Geometric linking

---

## 2. Volatility

### Realized Volatility

$$\sigma = \sqrt{\frac{1}{T-1}\sum_{t=1}^{T}(r_t - \bar{r})^2} \times \sqrt{N}$$

- **Method**: Sample standard deviation
- **ddof**: 1 (sample) or 0 (population)
- **Annualization**: $\times \sqrt{N}$

### Parkinson Volatility (Range-Based)

$$\sigma_P = \sqrt{\frac{1}{4T\ln(2)}\sum_{t=1}^{T}\ln\left(\frac{H_t}{L_t}\right)^2} \times \sqrt{N}$$

- **H**: High price
- **L**: Low price
- **Efficiency**: ~5x more efficient than close-to-close
- **Reference**: Parkinson (1980)

### Garman-Klass Volatility

$$\sigma_{GK} = \sqrt{\left[\frac{1}{2}\ln\left(\frac{H_t}{L_t}\right)^2 - (2\ln2-1)\ln\left(\frac{C_t}{O_t}\right)^2\right]} \times \sqrt{N}$$

- **O**: Open, **H**: High, **L**: Low, **C**: Close
- **Efficiency**: ~8x more efficient than close-to-close
- **Reference**: Garman & Klass (1980)

### Semi-Deviation (Downside Volatility)

$$\sigma_d = \sqrt{\frac{1}{T_d-1}\sum_{r_t<0}(r_t - \bar{r}_d)^2} \times \sqrt{N}$$

- **Only negative returns** are included
- **Use**: Sortino ratio, downside risk measurement

### Portfolio Volatility

$$\sigma_p = \sqrt{\mathbf{w}^T \Sigma \mathbf{w}} \times \sqrt{N}$$

- **w**: Weight vector
- **Σ**: Covariance matrix
- **Minimum observations**: > number of assets

---

## 3. Risk-Adjusted Returns

### Sharpe Ratio

$$SR = \frac{R_p - R_f}{\sigma_p}$$

- **R_p**: Portfolio annualized return
- **R_f**: Risk-free rate (default: 5%)
- **σ_p**: Portfolio annualized volatility
- **Reference**: Sharpe (1964)

### Sortino Ratio

$$\text{Sortino} = \frac{R_p - R_f}{\sigma_d}$$

- **σ_d**: Downside deviation
- **Use**: Penalizes only downside risk
- **Reference**: Sortino & van der Meer (1991)

### Calmar Ratio

$$\text{Calmar} = \frac{R_p}{|DD_{max}|}$$

- **DD_max**: Maximum drawdown (absolute value)
- **Minimum observations**: 36 months (3 years)

### Treynor Ratio

$$\text{Treynor} = \frac{R_p - R_f}{\beta_p}$$

- **β_p**: Portfolio beta relative to market
- **Minimum observations**: 30

### Information Ratio

$$IR = \frac{R_p - R_b}{TE}$$

- **R_b**: Benchmark return
- **TE**: Tracking error (annualized)
- **Reference**: Grinold & Kahn (1999)

### Omega Ratio

$$\Omega = \frac{\int_{-\infty}^{\theta}(F(r) - 1)dr}{\int_{\theta}^{\infty}(1 - F(r))dr}$$

- **θ**: Threshold return (default: 0%)
- **F(r)**: CDF of returns
- **Use**: Measures probability-weighted gains vs losses

---

## 4. Value at Risk

### Historical VaR

$$VaR_\alpha = -\text{percentile}(r, 1-\alpha)$$

- **Method**: Non-parametric percentile
- **Confidence**: 95% (default)
- **Horizon scaling**: $VaR_T = VaR_1 \times \sqrt{T}$

### Parametric VaR

$$VaR_\alpha = -(\mu + z_\alpha \sigma)$$

- **z_α**: Normal quantile
- **Assumes**: Normal distribution
- **Horizon scaling**: $\mu_T = \mu \times T$, $\sigma_T = \sigma \times \sqrt{T}$

### Modified VaR (Cornish-Fisher)

$$z_{CF} = z + \frac{z^2-1}{6}S + \frac{z^3-3z}{24}K - \frac{2z^3-5z}{36}S^2$$

- **S**: Skewness
- **K**: Excess kurtosis
- **Adjusts for**: Non-normality
- **Reference**: Cornish & Fisher (1937)

### CVaR (Expected Shortfall)

$$CVaR_\alpha = -E[r | r \leq -VaR_\alpha]$$

- **Always**: $CVaR \geq VaR$
- **Interpretation**: Average loss in worst $(1-\alpha)\%$ scenarios

---

## 5. Performance Attribution

### Linear Regression

$$r_{asset} = \alpha + \beta \cdot r_{benchmark} + \epsilon$$

- **β**: Sensitivity to benchmark (slope)
- **α**: Jensen's alpha (intercept)
- **R²**: Goodness of fit

### Tracking Error

$$TE = \text{std}(r_p - r_b) \times \sqrt{N}$$

- **Volatility of active returns**

### Alpha (Jensen's)

$$\alpha = R_p - [R_f + \beta(R_b - R_f)]$$

- **Annualized**: $\alpha_{ann} = \alpha_{daily} \times N$

---

## 6. Drawdown Analysis

### Drawdown Series

$$DD_t = \frac{P_t - P_{peak}}{P_{peak}}$$

- **P_peak**: Running maximum price
- **Range**: $(-\infty, 0]$

### Maximum Drawdown

$$DD_{max} = \min_t(DD_t)$$

- **Metrics**: Start, trough, recovery dates
- **Duration**: Days from peak to recovery

### Drawdown Duration

$$D = \text{days since last peak}$$

- **0** if at new high

---

## 7. Portfolio Calculations

### Market-Value Weights

$$w_i = \frac{qty_i \times price_i}{\sum_j qty_j \times price_j}$$

- **Use**: Risk exposure (current weights)
- **Cost weights**: Use $qty_i \times cost_i$ for allocation reporting

### NAV Reconstruction

$$NAV_t = \sum_i qty_i \times price_{i,t}$$

- **Positions**: Added at buy_date
- **Before buy_date**: Contribution = 0

### Diversification Ratio

$$DR = \frac{\sum_i w_i \sigma_i}{\sigma_p}$$

- **DR > 1**: Diversification benefit
- **DR = 1**: No benefit (perfect correlation)

---

## Data Requirements

| Metric | Minimum Observations | Data Type |
|--------|---------------------|-----------|
| Returns | 2 | Prices |
| Volatility | 2 | Returns |
| VaR/CVaR | 30 | Returns |
| Sharpe/Sortino | 30 | Returns |
| Beta/Alpha | 30 | Returns + Benchmark |
| Information Ratio | 30 | Returns + Benchmark |
| Drawdown | 2 | Prices |
| Portfolio Risk | > assets | Returns Matrix |

---

## References

1. Sharpe, W.F. (1964). "Capital Asset Prices." *Journal of Finance*.
2. Sortino, F.A. & van der Meer, R.H. (1991). "Downside Risk." *Journal of Portfolio Management*.
3. Grinold, R.C. & Kahn, R.N. (1999). *Active Portfolio Management*.
4. Parkinson, M. (1980). "The Extreme Value Method for Estimating Variance." *Journal of Business*.
5. Garman, M.B. & Klass, M.J. (1980). "On the Estimation of Security Price Volatilities." *Journal of Business*.
6. Cornish, E.A. & Fisher, R.A. (1937). "Moments and Cumulants in the Variate-Normal Distribution." *Royal Statistical Society*.
