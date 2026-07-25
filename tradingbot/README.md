# HA-ALMA-RSI-ATR Trading Bot — FastAPI Backend

A production-ready FastAPI backend for the **Heikin-Ashi + ALMA + RSI + ATR**
Binance Futures trading bot, designed for integration with a React frontend.

---

## Table of Contents

1. [Project Structure](#project-structure)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Configuration (.env)](#configuration-env)
5. [Running the Server](#running-the-server)
6. [API Reference](#api-reference)
   - [Root](#root)
   - [Configuration](#configuration)
   - [Bot Control](#bot-control)
   - [Market Data](#market-data)
   - [Backtesting](#backtesting)
   - [Technical Indicators](#technical-indicators)
   - [WebSockets](#websockets)
7. [React Integration Guide](#react-integration-guide)
8. [Running Tests](#running-tests)
9. [Data Persistence](#data-persistence)

---

## Project Structure

```
tradingbot/
├── app/
│   ├── main.py                  # FastAPI application entry-point
│   ├── core/
│   │   └── config.py            # Pydantic Settings (reads .env)
│   ├── api/
│   │   └── v1/
│   │       ├── router.py        # Mounts all sub-routers
│   │       ├── websockets.py    # WebSocket endpoints
│   │       └── endpoints/
│   │           ├── bot.py       # Bot start/stop/status/logs
│   │           ├── config.py    # Strategy configuration CRUD
│   │           ├── backtest.py  # Backtest execution + dataset list
│   │           ├── market_data.py # Download & fetch klines
│   │           └── indicators.py  # Signal & indicator calculation
│   ├── schemas/                 # Pydantic request/response models
│   ├── services/                # Business logic layer
│   └── trading_engine/          # Core strategy (bot.py, indicators.py, backtest.py)
├── data/                        # Runtime data (auto-created)
│   └── instances/
│       └── <SYMBOL>/
│           ├── config.json      # Per-symbol bot config
│           ├── bot_state.json   # Current bot state snapshot
│           ├── live_status.json # Live PnL / status snapshot
│           └── bot.log          # Bot log file
├── tests/
│   └── test_api.py              # Verification tests (pytest)
├── .env.example                 # Copy this to .env and fill in your keys
├── requirements.txt
└── pytest.ini
```

---

## Prerequisites

- Python **3.10+**
- A Binance **Futures** account (API key + secret for live trading)
- *(Optional)* Telegram bot token for notifications

---

## Installation

```bash
# 1. Clone / open the project
cd d:\tradingbot

# 2. Create and activate a virtual environment (optional but recommended)
python -m venv venv
venv\Scripts\activate        # Windows

# 3. Install dependencies
#    If your C: drive is low on space, redirect pip's cache to D:
pip install -r requirements.txt --cache-dir D:\pip_cache

# 4. Copy the example env file
copy .env.example .env
```

---

## Configuration (.env)

Edit `.env` with your credentials before starting the server:

```env
# Binance API Keys (required for live trading and data fetching)
BINANCE_API_KEY=your_binance_api_key_here
BINANCE_API_SECRET=your_binance_api_secret_here

# Telegram Notifications (optional)
TELEGRAM_BOT_TOKEN=123456:ABC-your-token-here
TELEGRAM_CHAT_ID=987654321

# CORS: comma-separated list of allowed React dev server origins
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# Directory where bot state, configs and logs are stored
DATA_DIR=data
```

> **Tip:** All settings can also be passed as environment variables directly
> (they take priority over the `.env` file).

---

## Running the Server

```bash
# Development (auto-reload on file change)
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

- Interactive API docs → http://localhost:8000/docs  
- Alternative docs (ReDoc) → http://localhost:8000/redoc  
- OpenAPI JSON → http://localhost:8000/api/v1/openapi.json

---

## API Reference

All REST endpoints are prefixed with **`/api/v1`**.

### Root

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Health-check / welcome message |

---

### Configuration

Base path: `/api/v1/config`

| Method | Path | Query params | Body | Description |
|--------|------|--------------|------|-------------|
| GET | `/api/v1/config` | `symbol` (default `BTCUSDT`) | — | Get current strategy config + editable field limits |
| PUT | `/api/v1/config` | `symbol` | `TradingConfigSchema` | Update strategy configuration |
| POST | `/api/v1/config/reset` | `symbol` | — | Reset configuration to defaults |

**Example response (`GET /api/v1/config`):**
```json
{
  "config": {
    "symbol": "BTCUSDT",
    "interval": "12h",
    "leverage": 5,
    "alma_window": 9,
    "rsi_period": 14,
    "rsi_sma_period": 14,
    "atr_period": 14,
    "adx_period": 14,
    "trend_sma_period": 50,
    ...
  },
  "limits": {
    "leverage": [1, 20, "int"],
    "alma_window": [3, 50, "int"],
    ...
  }
}
```

---

### Bot Control

Base path: `/api/v1/bot`

| Method | Path | Query params | Description |
|--------|------|--------------|-------------|
| GET | `/api/v1/bot/status` | `symbol`, `log_lines` (1–1000) | Get full bot status (running state, PnL, position) |
| POST | `/api/v1/bot/start` | `symbol` | Start the trading bot subprocess |
| POST | `/api/v1/bot/stop` | `symbol` | Gracefully stop the bot subprocess |
| GET | `/api/v1/bot/logs` | `symbol`, `lines` (1–2000) | Tail the bot log file |

**Example response (`GET /api/v1/bot/status`):**
```json
{
  "is_running": false,
  "symbol": "BTCUSDT",
  "position": null,
  "unrealized_pnl": 0.0,
  "last_updated": "2024-01-15T10:30:00",
  "logs": ["[INFO] Bot stopped at 10:30:00"]
}
```

---

### Market Data

Base path: `/api/v1/market`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/market/download` | Download historical klines from Binance and save locally as a CSV dataset |
| GET | `/api/v1/market/klines` | Fetch recent live klines (OHLCV) for charting |

**POST `/api/v1/market/download` request body:**
```json
{
  "symbol": "BTCUSDT",
  "interval": "12h",
  "months": 6,
  "filename": "btcusdt_12h_6mo.csv"
}
```

**GET `/api/v1/market/klines` query params:**
- `symbol` — e.g. `BTCUSDT`
- `interval` — e.g. `1h`, `4h`, `12h`
- `limit` — number of candles (1–1500)

---

### Backtesting

Base path: `/api/v1/backtest`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/backtest/datasets` | List all locally saved CSV datasets |
| POST | `/api/v1/backtest/run` | Run a backtest on a saved dataset |

**POST `/api/v1/backtest/run` request body:**
```json
{
  "dataset_name": "btcusdt_12h_6mo.csv",
  "initial_balance": 1000.0
}
```

**Example response:**
```json
{
  "total_trades": 47,
  "win_rate": 0.62,
  "total_pnl": 345.22,
  "max_drawdown": -12.5,
  "sharpe_ratio": 1.8,
  "trades": [...]
}
```

---

### Technical Indicators

Base path: `/api/v1/indicators`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/indicators/latest` | Get latest signal (LONG/SHORT/NEUTRAL) with indicator snapshot |
| POST | `/api/v1/indicators/calculate` | Calculate indicators over N recent candles |

**GET `/api/v1/indicators/latest` query params:**
- `symbol` — e.g. `BTCUSDT`
- `interval` — e.g. `12h`

**POST `/api/v1/indicators/calculate` request body:**
```json
{
  "symbol": "BTCUSDT",
  "interval": "12h",
  "klines_lookback": 200
}
```

---

### WebSockets

Base path: `/api/v1/ws`

| Path | Description |
|------|-------------|
| `ws://localhost:8000/api/v1/ws/status/{symbol}` | Streams bot status JSON every ~2 s |
| `ws://localhost:8000/api/v1/ws/logs/{symbol}` | Streams new log lines as they appear |

---

## React Integration Guide

### 1. Set the API base URL

```js
// src/api/config.js
export const API_BASE = "http://localhost:8000/api/v1";
```

### 2. Fetch bot status

```js
// src/api/bot.js
import { API_BASE } from "./config";

export async function getBotStatus(symbol = "BTCUSDT") {
  const res = await fetch(`${API_BASE}/bot/status?symbol=${symbol}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function startBot(symbol = "BTCUSDT") {
  const res = await fetch(`${API_BASE}/bot/start?symbol=${symbol}`, { method: "POST" });
  return res.json();
}

export async function stopBot(symbol = "BTCUSDT") {
  const res = await fetch(`${API_BASE}/bot/stop?symbol=${symbol}`, { method: "POST" });
  return res.json();
}
```

### 3. Live status via WebSocket

```js
// src/hooks/useBotStatus.js
import { useEffect, useState } from "react";

export function useBotStatus(symbol = "BTCUSDT") {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/api/v1/ws/status/${symbol}`);
    ws.onmessage = (e) => setStatus(JSON.parse(e.data));
    ws.onerror = () => ws.close();
    return () => ws.close();
  }, [symbol]);

  return status;
}
```

### 4. Fetch & display klines

```js
export async function getKlines(symbol, interval, limit = 100) {
  const params = new URLSearchParams({ symbol, interval, limit });
  const res = await fetch(`${API_BASE}/market/klines?${params}`);
  return res.json();  // Array of { open_time, open, high, low, close, close_time }
}
```

### 5. Update strategy config

```js
export async function updateConfig(symbol, configPayload) {
  const res = await fetch(`${API_BASE}/config?symbol=${symbol}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(configPayload),
  });
  return res.json();
}
```

---

## Running Tests

```bash
# Install test runner (redirect cache to D: if C: is low on space)
pip install pytest httpx --cache-dir D:\pip_cache

# Run the full test suite
pytest tests/ -v

# Run a specific test class
pytest tests/test_api.py::TestConfig -v

# Run with output
pytest tests/ -v -s
```

> All tests use FastAPI's built-in `TestClient` — **no running server needed**.  
> Tests that require a real Binance connection will gracefully return HTTP 500
> in a CI/offline environment and are still asserted to return valid JSON.

---

## Data Persistence

The backend persists all runtime data under the `DATA_DIR` folder (default: `data/`):

```
data/
└── instances/
    └── BTCUSDT/
        ├── config.json       ← Strategy settings (editable via API)
        ├── bot_state.json    ← Full bot state snapshot (written each cycle)
        ├── live_status.json  ← PnL / position snapshot (written each cycle)
        └── bot.log           ← Log file (tailable via API)
```

Each symbol runs in its own isolated instance directory, so you can safely
manage multiple bots simultaneously (e.g., BTCUSDT + ETHUSDT).
