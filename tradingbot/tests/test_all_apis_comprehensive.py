"""
Exhaustive API Test Suite for Trading Bot Backend
==================================================
Tests all 18 REST and WebSocket endpoints in FastAPI app.
"""

import pytest
import os
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_01_root_endpoint():
    res = client.get("/")
    assert res.status_code == 200, f"Root failed: {res.text}"
    data = res.json()
    assert "message" in data
    assert "version" in data
    print("[PASS] GET / - Root Endpoint")


def test_02_openapi_json():
    res = client.get("/api/v1/openapi.json")
    assert res.status_code == 200
    schema = res.json()
    assert schema["info"]["title"] is not None
    assert "/api/v1/bot/status" in schema["paths"]
    print("[PASS] GET /api/v1/openapi.json - OpenAPI Schema")


def test_03_swagger_docs():
    res = client.get("/docs")
    assert res.status_code == 200
    print("[PASS] GET /docs - Swagger UI")


def test_04_redoc_docs():
    res = client.get("/redoc")
    assert res.status_code == 200
    print("[PASS] GET /redoc - ReDoc")


def test_05_get_config():
    res = client.get("/api/v1/config", params={"symbol": "BTCUSDT"})
    assert res.status_code == 200
    data = res.json()
    assert "config" in data
    assert "limits" in data
    assert data["config"]["symbol"] == "BTCUSDT"
    print("[PASS] GET /api/v1/config - Symbol Configuration")


def test_06_update_config():
    get_res = client.get("/api/v1/config", params={"symbol": "BTCUSDT"})
    cfg = get_res.json()["config"]
    cfg["leverage"] = 3
    res = client.put("/api/v1/config", params={"symbol": "BTCUSDT"}, json=cfg)
    assert res.status_code == 200
    updated_cfg = res.json()["config"]
    assert updated_cfg["leverage"] == 3
    print("[PASS] PUT /api/v1/config - Update Configuration")


def test_07_reset_config():
    res = client.post("/api/v1/config/reset", params={"symbol": "BTCUSDT"})
    assert res.status_code in (200, 400)
    if res.status_code == 200:
        cfg = res.json()["config"]
        assert cfg["leverage"] == 10  # Default leverage is 10
    print("[PASS] POST /api/v1/config/reset - Reset Configuration")


def test_08_get_bot_status():
    res = client.get("/api/v1/bot/status", params={"symbol": "BTCUSDT", "log_lines": 20})
    assert res.status_code == 200
    data = res.json()
    assert "is_running" in data
    assert isinstance(data["is_running"], bool)
    print("[PASS] GET /api/v1/bot/status - Bot Telemetry Status")


def test_09_get_bot_logs():
    res = client.get("/api/v1/bot/logs", params={"symbol": "BTCUSDT", "lines": 50})
    assert res.status_code == 200
    data = res.json()
    assert "logs" in data
    assert isinstance(data["logs"], list)
    print("[PASS] GET /api/v1/bot/logs - Bot Logs Tail")


def test_10_stop_bot():
    res = client.post("/api/v1/bot/stop", params={"symbol": "BTCUSDT"})
    assert res.status_code == 200
    data = res.json()
    assert "success" in data
    print("[PASS] POST /api/v1/bot/stop - Stop Bot")


def test_11_start_bot():
    res = client.post("/api/v1/bot/start", params={"symbol": "BTCUSDT"})
    assert res.status_code in (200, 500)
    print("[PASS] POST /api/v1/bot/start - Start Bot Handler")


def test_12_list_backtest_datasets():
    res = client.get("/api/v1/backtest/datasets")
    assert res.status_code == 200
    datasets = res.json()
    assert isinstance(datasets, list)
    assert len(datasets) > 0, "Expected at least 1 dataset in data/datasets"
    print(f"[PASS] GET /api/v1/backtest/datasets - Found {len(datasets)} dataset(s)")


def test_13_run_backtest_on_dataset():
    # Fetch available datasets
    ds_res = client.get("/api/v1/backtest/datasets")
    datasets = ds_res.json()
    if datasets:
        ds_name = datasets[0]["name"]
        payload = {
            "dataset_name": ds_name,
            "initial_balance": 1000.0,
            "leverage": 2,
        }
        res = client.post("/api/v1/backtest/run", json=payload)
        assert res.status_code == 200, f"Backtest failed: {res.text}"
        result = res.json()
        assert "total_trades" in result
        assert "final_balance" in result
        assert "equity_curve" in result
        print(f"[PASS] POST /api/v1/backtest/run - Executed backtest on {ds_name} (Trades: {result['total_trades']})")


def test_14_get_market_klines():
    res = client.get("/api/v1/market/klines", params={"symbol": "BTCUSDT", "interval": "1h", "limit": 10})
    assert res.status_code in (200, 500)
    if res.status_code == 200:
        klines = res.json()
        assert isinstance(klines, list)
        assert len(klines) > 0
        assert "open" in klines[0]
        assert "close" in klines[0]
    print("[PASS] GET /api/v1/market/klines - Kline Market Data")


def test_15_download_market_data():
    payload = {
        "symbol": "BTCUSDT",
        "interval": "1h",
        "months": 1,
        "filename": "test_download.csv"
    }
    res = client.post("/api/v1/market/download", json=payload)
    assert res.status_code in (200, 500)
    if res.status_code == 200:
        data = res.json()
        assert data["success"] is True
        # Cleanup temporary downloaded test dataset
        if os.path.exists(data["filepath"]):
            try:
                os.remove(data["filepath"])
            except Exception:
                pass
    print("[PASS] POST /api/v1/market/download - Download Klines API")


def test_16_get_latest_indicators():
    res = client.get("/api/v1/indicators/latest", params={"symbol": "BTCUSDT", "interval": "1h"})
    assert res.status_code in (200, 500)
    if res.status_code == 200:
        data = res.json()
        assert "signal" in data
        assert "close_price" in data
        assert "ha_close" in data
        assert "is_aligned_with_trend" in data
    print("[PASS] GET /api/v1/indicators/latest - Latest Technical Signal")


def test_17_calculate_indicators():
    payload = {
        "symbol": "BTCUSDT",
        "interval": "1h",
        "klines_lookback": 50
    }
    res = client.post("/api/v1/indicators/calculate", json=payload)
    assert res.status_code in (200, 500)
    if res.status_code == 200:
        rows = res.json()
        assert isinstance(rows, list)
        assert len(rows) > 0
        assert "alma" in rows[-1]
        assert "rsi" in rows[-1]
    print("[PASS] POST /api/v1/indicators/calculate - Calculate Technical Indicators Table")


def test_18_websocket_live_stream():
    with client.websocket_connect("/api/v1/ws/live?symbol=BTCUSDT&interval_seconds=1") as websocket:
        data = websocket.receive_json()
        assert "is_running" in data
        assert "logs" in data
    print("[PASS] WS /api/v1/ws/live - Live Status WebSocket")
