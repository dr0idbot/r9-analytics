-- ============================================================================
-- r9_analytics — Market Data Schema
-- Phase 1: TABLE DESIGN
-- All fact tables reference tickers.ticker. tickers holds CONSTANT metadata only;
-- mutable sync markers live in ticker_sync so tickers never changes after insert.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS market;

-- ----------------------------------------------------------------------------
-- tickers: constant, slow-changing reference metadata from yfinance .info
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market.tickers (
    ticker         TEXT PRIMARY KEY,
    name           TEXT,            -- shortName / longName
    sector         TEXT,
    industry       TEXT,
    currency       TEXT,
    exchange       TEXT,            -- exchange code (e.g. NMS, NYS)
    exchange_name  TEXT,            -- human readable exchange
    country        TEXT,
    timezone       TEXT,            -- e.g. America/New_York
    quote_type     TEXT,            -- EQUITY / ETF / INDEX
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- ticker_sync: mutable per-ticker sync bookkeeping (NOT constant)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market.ticker_sync (
    ticker         TEXT PRIMARY KEY REFERENCES market.tickers(ticker) ON DELETE CASCADE,
    last_synced_on DATE,            -- last time we attempted/completed a sync
    last_candle_date DATE,          -- last trade_date present in daily_candles
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- daily_candles: OHLCV per ticker per trade day (core time series)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market.daily_candles (
    ticker     TEXT NOT NULL REFERENCES market.tickers(ticker) ON DELETE CASCADE,
    trade_date DATE NOT NULL,
    open       DOUBLE PRECISION,
    high       DOUBLE PRECISION,
    low        DOUBLE PRECISION,
    close      DOUBLE PRECISION,
    adj_close  DOUBLE PRECISION,
    volume     BIGINT,
    PRIMARY KEY (ticker, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_candles_date ON market.daily_candles (trade_date);

-- ----------------------------------------------------------------------------
-- dividends: per-ticker cash dividend events
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market.dividends (
    ticker     TEXT NOT NULL REFERENCES market.tickers(ticker) ON DELETE CASCADE,
    pay_date   DATE NOT NULL,
    amount     DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (ticker, pay_date)
);

-- ----------------------------------------------------------------------------
-- splits: per-ticker stock-split events
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market.splits (
    ticker     TEXT NOT NULL REFERENCES market.tickers(ticker) ON DELETE CASCADE,
    split_date DATE NOT NULL,
    ratio      DOUBLE PRECISION NOT NULL,   -- e.g. 2.0 means 2:1 split
    PRIMARY KEY (ticker, split_date)
);
