# Trading Bot API Documentation

A REST API for controlling the Binance Futures HA-ALMA Trading Bot. Built with FastAPI.

> **Base URL:** `http://localhost:8000`  
> **API Prefix:** `/api/v1`  
> **Interactive Docs (Swagger UI):** `http://localhost:8000/docs`  
> **Alternative Docs (ReDoc):** `http://localhost:8000/redoc`

---

## Table of Contents

- [Root](#root)
- [Bot Control](#bot-control)
  - [GET /api/v1/bot/status](#get-apiv1botstatus)
  - [POST /api/v1/bot/start](#post-apiv1botstart)
  - [POST /api/v1/bot/stop](#post-apiv1botstop)
  - [GET /api/v1/bot/logs](#get-apiv1botlogs)
- [Configuration](#configuration)
  - [GET /api/v1/config](#get-apiv1config)
  - [PUT /api/v1/config](#put-apiv1config)
  - [POST /api/v1/config/reset](#post-apiv1configreset)
- [Backtesting](#backtesting)
  - [POST /api/v1/backtest/run](#post-apiv1backtestrun)
  - [GET /api/v1/backtest/datasets](#get-apiv1backtestdatasets)
- [Market Data](#market-data)
  - [POST /api/v1/market/download](#post-apiv1marketdownload)
  - [GET /api/v1/market/klines](#get-apiv1marketklines)
- [Technical Indicators](#technical-indicators)
  - [GET /api/v1/indicators/latest](#get-apiv1indicatorslatest)
  - [POST /api/v1/indicators/calculate](#post-apiv1indicatorscalculate)
- [WebSockets](#websockets)
  - [WS /api/v1/ws/live](#ws-apiv1wslive)

---

## Root

### `GET /`

**Description:** Health check endpoint. Returns a welcome message, the Swagger docs URL, and the current API version. Useful for verifying the server is running.

**Response:**
```json
{
  "message": "Welcome to the Binance Futures HA-ALMA Bot API",
  "docs_url": "/docs",
  "version": "1.0.0"
}
```

---

## Bot Control

Endpoints for starting, stopping, and monitoring the trading bot subprocess for a given symbol.

---

### `GET /api/v1/bot/status`

**Description:** Returns the current status of the trading bot for a specific symbol, including whether it is running, its internal trading state (position, order IDs, ATR, signal candle time, TP level), the live exchange status (position amount, entry/mark prices, unrealized PnL, SL/TP prices, balance, leverage), and recent log lines.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | `"BTCUSDT"` | The trading symbol to query |
| `log_lines` | integer | `50` | Number of recent log lines to include (1–1000) |

**Response (`200 OK`):**
```json
{
  "is_running": true,
  "bot_state": {
    "status": "LONG",
    "direction": "LONG",
    "entry1_order_id": 12345,
    "entry2_order_id": 12346,
    "sl_order_id": 12347,
    "tp_order_id": 12348,
    "atr_at_signal": 1500.5,
    "signal_candle_time": 1690000000000,
    "tp_level": 1
  },
  "live_status": {
    "timestamp": 1690000000.0,
    "symbol": "BTCUSDT",
    "interval": "12h",
    "position_amt": 0.001,
    "entry_price": 29500.0,
    "mark_price": 29600.0,
    "unrealized_pnl": 10.0,
    "sl_price": 28000.0,
    "tp_price": 31000.0,
    "tp_qty": 0.0003,
    "tp_level": 1,
    "balance": 10000.0,
    "leverage": 10,
    "testnet": true,
    "reconciled_at": 1690000000.0
  },
  "logs": ["2024-07-24 INFO Starting bot...", "..."]
}
```

---

### `POST /api/v1/bot/start`

**Description:** Launches the trading bot as a background subprocess for the specified symbol. The bot reads its configuration from the symbol's `config.json`, begins polling for candle data, and executes trades on Binance Futures (testnet or live depending on config). Returns an error if the bot is already running for that symbol.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | `"BTCUSDT"` | The trading symbol to start the bot for |

**Response (`200 OK`):**
```json
{
  "success": true,
  "message": "Trading bot for BTCUSDT started successfully."
}
```

**Errors:**
- `400` — Bot is already running for the given symbol.
- `500` — Failed to start the subprocess.

---

### `POST /api/v1/bot/stop`

**Description:** Terminates the trading bot subprocess for the specified symbol. The bot will gracefully close any open positions before shutting down if configured to do so. Returns an error if no bot process is found for that symbol.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | `"BTCUSDT"` | The trading symbol to stop the bot for |

**Response (`200 OK`):**
```json
{
  "success": true,
  "message": "Trading bot for BTCUSDT stopped successfully."
}
```

**Errors:**
- `400` — Bot is not running for the given symbol.
- `500` — Failed to stop the subprocess.

---

### `GET /api/v1/bot/logs`

**Description:** Fetches the last N lines from the bot's log file for a given symbol. Useful for debugging and monitoring bot activity without accessing the server filesystem directly.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | `"BTCUSDT"` | The trading symbol whose logs to retrieve |
| `lines` | integer | `100` | Number of log lines to return from the end of the file (1–2000) |

**Response (`200 OK`):**
```json
{
  "logs": ["2024-07-24 12:00:00 INFO Bot started", "2024-07-24 12:00:01 INFO Polling..."],
  "line_count": 2
}
```

---

## Configuration

Endpoints for reading and updating the trading strategy configuration for a symbol. Configuration is persisted per symbol in `data/instances/{SYMBOL}/config.json`.

---

### `GET /api/v1/config`

**Description:** Retrieves the full trading configuration for a symbol, including all strategy parameters (leverage, margin fractions, indicator periods, SL/TP settings, ADX filter, etc.) and a `limits` object that defines the valid range and type for each configurable field. Use the limits to build dynamic forms or validate user input.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | `"BTCUSDT"` | The trading symbol to retrieve config for |

**Response (`200 OK`):**
```json
{
  "config": {
    "testnet": true,
    "symbol": "BTCUSDT",
    "interval": "12h",
    "leverage": 10,
    "margin_fraction_per_entry": 0.25,
    "margin_fraction_counter_trend": 0.20,
    "trend_sma_period": 50,
    "alma_window": 9,
    "rsi_period": 14,
    "rsi_sma_period": 14,
    "atr_period": 14,
    "sl_atr_multiple": 1.0,
    "tp_custom_levels": "0.5",
    "tp_step_atr": 0.5,
    "tp_close_fraction": 0.30,
    "sl_trail_gap_atr": 0.5,
    "adx_filter_enabled": false,
    "adx_period": 14,
    "adx_threshold": 25.0,
    "poll_seconds": 15,
    "klines_lookback": 300,
    "telegram_enabled": true
  },
  "limits": {
    "leverage": [1, 125, "int"],
    "margin_fraction_per_entry": [0.01, 1.0, "float"],
    "alma_window": [2, 200, "int"],
    "rsi_period": [2, 200, "int"],
    "rsi_sma_period": [2, 200, "int"],
    "atr_period": [2, 200, "int"],
    "sl_atr_multiple": [0.1, 10.0, "float"],
    "tp_step_atr": [0.05, 10.0, "float"],
    "tp_close_fraction": [0.05, 0.95, "float"],
    "sl_trail_gap_atr": [0.05, 10.0, "float"],
    "adx_period": [2, 200, "int"],
    "adx_threshold": [0.0, 100.0, "float"],
    "poll_seconds": [1, 3600, "int"],
    "klines_lookback": [50, 1500, "int"],
    "trend_sma_period": [2, 500, "int"]
  }
}
```

---

### `PUT /api/v1/config`

**Description:** Updates the trading configuration for a symbol. Supports partial updates — only include the fields you want to change. Attempting to change `symbol` or `interval` while the bot is running will return a `400` error. Changes are persisted to disk immediately.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | `"BTCUSDT"` | The trading symbol to update config for |

**Request Body (all fields optional):**
```json
{
  "testnet": false,
  "leverage": 20,
  "alma_window": 12,
  "rsi_period": 14,
  "sl_atr_multiple": 1.5,
  "tp_custom_levels": "0.5,1.0,1.5",
  "adx_filter_enabled": true,
  "adx_threshold": 30.0,
  "poll_seconds": 30,
  "klines_lookback": 500,
  "telegram_enabled": false
}
```

**Response (`200 OK`):** Returns the updated config and limits (same schema as `GET /api/v1/config`).

**Errors:**
- `400` — Cannot change `symbol` or `interval` while the bot is running.
- `422` — Validation error (e.g., value out of range).

---

### `POST /api/v1/config/reset`

**Description:** Resets all trading configuration parameters to their default values for a given symbol. The `symbol` and `interval` fields are preserved. Cannot be performed while the bot is running.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | `"BTCUSDT"` | The trading symbol to reset config for |

**Response (`200 OK`):** Returns the reset config and limits (same schema as `GET /api/v1/config`).

**Errors:**
- `400` — Bot is currently running for the given symbol.

---

## Backtesting

Endpoints for running strategy backtests against historical data and listing available datasets.

---

### `POST /api/v1/backtest/run`

**Description:** Executes a full backtest using the HA-ALMA trading strategy on a historical CSV dataset. Optionally override any strategy parameter (leverage, indicator periods, SL/TP settings, etc.) for the backtest run — overrides do not affect the saved config. Returns comprehensive results including total return, win rate, monthly PnL breakdown, close-reason distribution, full equity curve, and individual trade logs.

**Request Body:**
```json
{
  "dataset_name": "btcusdt_12h_12m.csv",
  "starting_balance": 10000.0,
  "leverage": 10,
  "margin_fraction_per_entry": 0.25,
  "margin_fraction_counter_trend": 0.20,
  "trend_sma_period": 50,
  "alma_window": 9,
  "rsi_period": 14,
  "rsi_sma_period": 14,
  "atr_period": 14,
  "sl_atr_multiple": 1.0,
  "tp_custom_levels": "0.5",
  "tp_step_atr": 0.5,
  "tp_close_fraction": 0.30,
  "sl_trail_gap_atr": 0.5
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `dataset_name` | string | Yes | Filename of the CSV dataset in `data/datasets/` |
| `starting_balance` | float | No | Initial account balance (default: `10000.0`) |
| `leverage` | integer | No | Leverage multiplier (1–125) |
| `margin_fraction_per_entry` | float | No | Fraction of balance used per entry (0.01–1.0) |
| `margin_fraction_counter_trend` | float | No | Margin fraction for counter-trend entries |
| `trend_sma_period` | integer | No | Period for the trend-following SMA filter |
| `alma_window` | integer | No | ALMA indicator window size |
| `rsi_period` | integer | No | RSI calculation period |
| `rsi_sma_period` | integer | No | SMA smoothing period applied to RSI |
| `atr_period` | integer | No | ATR calculation period |
| `sl_atr_multiple` | float | No | Stop-loss distance as a multiple of ATR |
| `tp_custom_levels` | string | No | Comma-separated TP level multipliers (e.g. `"0.5,1.0,1.5"`) |
| `tp_step_atr` | float | No | ATR multiple between TP levels |
| `tp_close_fraction` | float | No | Fraction of position to close at each TP level |
| `sl_trail_gap_atr` | float | No | Trailing stop gap as a multiple of ATR |

> All strategy fields are optional. If omitted, the value from the symbol's saved configuration is used.

**Response (`200 OK`):**
```json
{
  "dataset_name": "btcusdt_12h_12m.csv",
  "starting_balance": 10000.0,
  "final_balance": 12345.67,
  "total_return_pct": 23.45,
  "total_trades": 150,
  "win_rate_pct": 58.67,
  "wins_count": 88,
  "losses_count": 62,
  "monthly_pnl": {
    "2024-01": 234.56,
    "2024-02": -120.00
  },
  "close_reasons": {
    "SL": 50,
    "TP_FINAL": 70,
    "REVERSAL": 30
  },
  "equity_curve": [
    {"timestamp": "2023-08-01T00:00:00+00:00", "balance": 10000.0},
    {"timestamp": "2023-08-12T00:00:00+00:00", "balance": 10150.0}
  ],
  "trades": [
    {
      "direction": "LONG",
      "signal_time": "2023-08-01T00:00:00+00:00",
      "entry_price": 29500.0,
      "qty": 0.001,
      "tp_level": 1,
      "realized_pnl": 15.0,
      "fees_paid": 2.0,
      "close_time": "2023-08-05T12:00:00+00:00",
      "close_reason": "TP_FINAL"
    }
  ]
}
```

---

### `GET /api/v1/backtest/datasets`

**Description:** Lists all available historical CSV dataset files stored in `data/datasets/`. Returns file metadata including name, size, last modified date, and full filesystem path. Use this to populate a dataset selector in the frontend.

**Response (`200 OK`):**
```json
[
  {
    "name": "btcusdt_12h_12m.csv",
    "size_bytes": 524288,
    "last_modified": "2024-07-24T12:00:00+00:00",
    "filepath": "D:\\tradingbot\\data\\datasets\\btcusdt_12h_12m.csv"
  }
]
```

---

## Market Data

Endpoints for downloading historical kline data and fetching live candle data from Binance Futures.

---

### `POST /api/v1/market/download`

**Description:** Downloads historical kline (OHLCV candlestick) data from the Binance Futures API for a given symbol and interval, and saves it as a CSV file in `data/datasets/`. The download is paginated automatically — the endpoint fetches all available data going back the specified number of months. Use this to create datasets for backtesting.

**Request Body:**
```json
{
  "symbol": "BTCUSDT",
  "interval": "12h",
  "months": 12,
  "filename": "btcusdt_12h_12m.csv"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `symbol` | string | No | `"BTCUSDT"` | Trading pair symbol |
| `interval` | string | No | `"12h"` | Kline interval (e.g. `1m`, `5m`, `1h`, `4h`, `12h`, `1d`) |
| `months` | integer | No | `12` | How many months of historical data to download (1–60) |
| `filename` | string | No | Auto-generated | Output filename (auto-generated as `{symbol}_{interval}_{months}m.csv` if omitted) |

**Response (`200 OK`):**
```json
{
  "success": true,
  "message": "Successfully downloaded 3650 candles for BTCUSDT (12h)",
  "filename": "btcusdt_12h_12m.csv",
  "filepath": "D:\\tradingbot\\data\\datasets\\btcusdt_12h_12m.csv",
  "rows_count": 3650
}
```

**Errors:**
- `502` — Failed to fetch data from Binance API.
- `500` — Error writing file to disk.

---

### `GET /api/v1/market/klines`

**Description:** Fetches the latest N raw kline (OHLCV) candles directly from Binance Futures for a given symbol and interval. Returns the open time, OHLC prices, and close time for each candle. Useful for building real-time charts or dashboards.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | `"BTCUSDT"` | Trading pair symbol |
| `interval` | string | `"12h"` | Kline interval |
| `limit` | integer | `100` | Number of candles to fetch (1–1500) |

**Response (`200 OK`):**
```json
[
  {
    "open_time": 1690000000000,
    "open": 29500.0,
    "high": 29800.0,
    "low": 29300.0,
    "close": 29700.0,
    "close_time": 1690043200000
  }
]
```

---

## Technical Indicators

Endpoints for computing technical indicators (HA candles, ALMA, RSI, ATR, ADX, trend SMA) from live Binance kline data.

---

### `GET /api/v1/indicators/latest`

**Description:** Fetches the latest klines from Binance and computes all trading indicators in real-time to produce the current trading signal (`LONG`, `SHORT`, or `None`). Returns a snapshot of all indicator values at the most recent closed candle, including Heikin-Ashi prices, ALMA, RSI, RSI-SMA, ATR, ADX, trend SMA, and whether the signal is aligned with the broader trend. Ideal for a dashboard overview or signal alerting.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | `"BTCUSDT"` | Trading pair symbol |
| `interval` | string | `"12h"` | Kline interval |

**Response (`200 OK`):**
```json
{
  "timestamp": "2024-07-24T00:00:00+00:00",
  "symbol": "BTCUSDT",
  "interval": "12h",
  "signal": "LONG",
  "close_price": 29700.0,
  "ha_close": 29650.0,
  "alma": 29600.0,
  "rsi": 55.3,
  "rsi_sma": 52.1,
  "atr": 450.0,
  "adx": 28.5,
  "trend_sma": 29200.0,
  "is_aligned_with_trend": true
}
```

---

### `POST /api/v1/indicators/calculate`

**Description:** Fetches the latest klines from Binance and returns a full table of computed indicator values for all recent candles (up to the specified lookback period). Each row contains the raw OHLCV data plus all derived indicators: Heikin-Ashi OHLC, ALMA, RSI, RSI-SMA, ATR, ADX, and trend SMA. Useful for charting indicators or performing offline analysis.

**Request Body:**
```json
{
  "symbol": "BTCUSDT",
  "interval": "12h",
  "klines_lookback": 300
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `symbol` | string | No | `"BTCUSDT"` | Trading pair symbol |
| `interval` | string | No | `"12h"` | Kline interval |
| `klines_lookback` | integer | No | `300` | Number of historical candles to include (50–1500) |

**Response (`200 OK`):**
```json
[
  {
    "timestamp": "2024-01-01T00:00:00+00:00",
    "open": 29500.0,
    "high": 29800.0,
    "low": 29300.0,
    "close": 29700.0,
    "ha_open": 29600.0,
    "ha_high": 29750.0,
    "ha_low": 29450.0,
    "ha_close": 29680.0,
    "alma": 29600.0,
    "rsi": 55.3,
    "rsi_sma": 52.1,
    "atr": 450.0,
    "adx": 28.5,
    "trend_sma": 29200.0
  }
]
```

---

## WebSockets

Persistent WebSocket connections for real-time data streaming.

---

### `WS /api/v1/ws/live`

**Description:** Opens a persistent WebSocket connection that streams live bot status updates at a configurable polling interval. The server pushes a JSON payload (same schema as the `GET /api/v1/bot/status` response) at regular intervals. The client does not need to send any messages — this is a one-way stream. Ideal for building real-time dashboards that display live position data, PnL, and logs without constant HTTP polling.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | `"BTCUSDT"` | The trading symbol to monitor |
| `interval_seconds` | integer | `2` | Polling interval in seconds (1–10) |

**Server Push (JSON, repeated at interval):**
```json
{
  "is_running": true,
  "bot_state": {
    "status": "LONG",
    "direction": "LONG",
    "entry1_order_id": 12345,
    "entry2_order_id": null,
    "sl_order_id": 12347,
    "tp_order_id": 12348,
    "atr_at_signal": 1500.5,
    "signal_candle_time": 1690000000000,
    "tp_level": 1
  },
  "live_status": {
    "timestamp": 1690000000.0,
    "symbol": "BTCUSDT",
    "interval": "12h",
    "position_amt": 0.001,
    "entry_price": 29500.0,
    "mark_price": 29600.0,
    "unrealized_pnl": 10.0,
    "sl_price": 28000.0,
    "tp_price": 31000.0,
    "tp_qty": 0.0003,
    "tp_level": 1,
    "balance": 10000.0,
    "leverage": 10,
    "testnet": true,
    "reconciled_at": 1690000000.0
  },
  "logs": ["2024-07-24 INFO ...", "..."]
}
```

---

## Quick Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check / welcome message |
| `GET` | `/api/v1/bot/status` | Get bot running state, internal state, exchange status, logs |
| `POST` | `/api/v1/bot/start` | Start the trading bot for a symbol |
| `POST` | `/api/v1/bot/stop` | Stop the trading bot for a symbol |
| `GET` | `/api/v1/bot/logs` | Tail the last N lines of bot logs |
| `GET` | `/api/v1/config` | Get full trading config + validation limits |
| `PUT` | `/api/v1/config` | Update trading config (partial update) |
| `POST` | `/api/v1/config/reset` | Reset config to defaults |
| `POST` | `/api/v1/backtest/run` | Run a backtest with optional strategy overrides |
| `GET` | `/api/v1/backtest/datasets` | List available historical CSV datasets |
| `POST` | `/api/v1/market/download` | Download historical klines from Binance |
| `GET` | `/api/v1/market/klines` | Fetch latest N raw klines for charting |
| `GET` | `/api/v1/indicators/latest` | Get latest computed trading signal + indicator values |
| `POST` | `/api/v1/indicators/calculate` | Get full historical table of computed indicators |
| `WS` | `/api/v1/ws/live` | Real-time streaming bot status via WebSocket |
