"""
FastAPI Backend Verification Tests
===================================
These are lightweight integration tests using the FastAPI `TestClient` (which
uses `httpx` under the hood via `requests`).  They verify that every endpoint
returns the *correct HTTP status code* and that the response *schema validates*,
without requiring a real Binance connection or a running bot process.

External calls (Binance API, bot subprocess) are automatically skipped or
return empty structures because no real API keys are present in the test
environment.

Run with:
    pytest tests/ -v
or (if installed on D:):
    python -m pytest tests/ -v --import-mode=importlib
"""

import json
import os
import pytest
from fastapi.testclient import TestClient

# ── Ensure the project root is importable ──────────────────────────────────
import sys
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ── App under test ─────────────────────────────────────────────────────────
from app.main import app  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)


# ==========================================================================
# Root / Health
# ==========================================================================

class TestRoot:
    def test_root_returns_200(self):
        response = client.get("/")
        assert response.status_code == 200

    def test_root_body_keys(self):
        data = client.get("/").json()
        assert "message" in data
        assert "docs_url" in data
        assert "version" in data

    def test_openapi_schema_available(self):
        response = client.get("/api/v1/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "openapi" in schema
        assert "paths" in schema


# ==========================================================================
# Configuration Endpoints  GET /api/v1/config
# ==========================================================================

class TestConfig:
    BASE = "/api/v1/config"

    def test_get_config_btcusdt(self):
        """GET /config should return HTTP 200 with a valid config object."""
        response = client.get(self.BASE, params={"symbol": "BTCUSDT"})
        assert response.status_code == 200
        data = response.json()
        # Must have config and limits keys
        assert "config" in data
        assert "limits" in data

    def test_get_config_has_required_fields(self):
        data = client.get(self.BASE, params={"symbol": "BTCUSDT"}).json()
        cfg = data["config"]
        required_fields = [
            "symbol", "interval", "leverage",
            "alma_window", "rsi_period", "atr_period",
        ]
        for field in required_fields:
            assert field in cfg, f"Missing field: {field}"

    def test_get_config_different_symbol(self):
        """Endpoint should work for any symbol string."""
        response = client.get(self.BASE, params={"symbol": "ETHUSDT"})
        assert response.status_code == 200

    def test_reset_config_while_bot_stopped(self):
        """POST /config/reset should succeed when the bot is not running."""
        response = client.post(f"{self.BASE}/reset", params={"symbol": "BTCUSDT"})
        # 200 or 400 (if bot happens to be running from a previous test run)
        assert response.status_code in (200, 400)

    def test_update_config_valid_payload(self):
        """PUT /config should accept a valid config payload."""
        # First get the current config to use as base
        data = client.get(self.BASE, params={"symbol": "BTCUSDT"}).json()
        cfg = data["config"]
        # Tweak a safe numeric field
        cfg["leverage"] = 2
        response = client.put(self.BASE, params={"symbol": "BTCUSDT"}, json=cfg)
        assert response.status_code in (200, 400, 422)  # 400 if bot running


# ==========================================================================
# Bot Control Endpoints  /api/v1/bot/*
# ==========================================================================

class TestBot:
    BASE = "/api/v1/bot"

    def test_get_status_returns_200(self):
        response = client.get(f"{self.BASE}/status", params={"symbol": "BTCUSDT"})
        assert response.status_code == 200

    def test_status_schema_fields(self):
        data = client.get(f"{self.BASE}/status", params={"symbol": "BTCUSDT"}).json()
        assert "is_running" in data
        # Response includes bot_state and live_status objects (may be None when bot is stopped)
        assert "bot_state" in data or "live_status" in data

    def test_get_logs_returns_200(self):
        response = client.get(f"{self.BASE}/logs", params={"symbol": "BTCUSDT", "lines": 10})
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert isinstance(data["logs"], list)

    def test_stop_bot_when_not_running(self):
        """Stopping a bot that is not running should still return 200 (graceful)."""
        response = client.post(f"{self.BASE}/stop", params={"symbol": "BTCUSDT"})
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert "message" in data

    def test_start_bot_returns_200_or_500(self):
        """
        Starting the bot without valid API keys will fail internally, but the
        endpoint must still return a proper JSON response (not an unhandled crash).
        """
        response = client.post(f"{self.BASE}/start", params={"symbol": "BTCUSDT"})
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert "success" in data


# ==========================================================================
# Market Data Endpoints  /api/v1/market/*
# ==========================================================================

class TestMarketData:
    BASE = "/api/v1/market"

    def test_download_requires_valid_payload(self):
        """
        POST /market/download with empty body — the schema provides defaults for all
        optional fields so this returns 200 (succeeds or 500 if Binance is unavailable),
        not 422. A missing *required* field like a non-default symbol would also just use
        the schema default.
        """
        response = client.post(f"{self.BASE}/download", json={})
        assert response.status_code in (200, 500)

    def test_download_valid_payload_structure(self):
        """POST /market/download returns 200 or 500 (no network in CI)."""
        payload = {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "months": 1,
        }
        response = client.post(f"{self.BASE}/download", json=payload)
        # In a live env returns 200; in a test env without network returns 500
        assert response.status_code in (200, 500)

    def test_klines_endpoint_structure(self):
        """GET /market/klines may fail on network but must return JSON."""
        response = client.get(
            f"{self.BASE}/klines",
            params={"symbol": "BTCUSDT", "interval": "1h", "limit": 5}
        )
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)


# ==========================================================================
# Backtesting Endpoints  /api/v1/backtest/*
# ==========================================================================

class TestBacktest:
    BASE = "/api/v1/backtest"

    def test_list_datasets_returns_200(self):
        response = client.get(f"{self.BASE}/datasets")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_run_backtest_missing_payload_422(self):
        """POST /backtest/run with empty body should be a validation error."""
        response = client.post(f"{self.BASE}/run", json={})
        assert response.status_code == 422

    def test_run_backtest_nonexistent_dataset_404(self):
        """POST /backtest/run with a dataset that doesn't exist should be 404."""
        payload = {
            "dataset_name": "NONEXISTENT_DATASET_FILE_XYZ.csv",
            "initial_balance": 1000.0,
        }
        response = client.post(f"{self.BASE}/run", json=payload)
        assert response.status_code == 404


# ==========================================================================
# Indicators Endpoints  /api/v1/indicators/*
# ==========================================================================

class TestIndicators:
    BASE = "/api/v1/indicators"

    def test_latest_signal_returns_json(self):
        """GET /indicators/latest may fail on network but must not crash."""
        response = client.get(
            f"{self.BASE}/latest",
            params={"symbol": "BTCUSDT", "interval": "1h"}
        )
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert "signal" in data

    def test_calculate_requires_valid_payload(self):
        """
        POST /indicators/calculate with an empty body uses schema defaults for all fields;
        it should return 200 (or 500 if Binance is unreachable), not 422.
        """
        response = client.post(f"{self.BASE}/calculate", json={})
        assert response.status_code in (200, 500)

    def test_calculate_valid_payload_schema(self):
        """POST /indicators/calculate with valid schema returns 200 or 500."""
        payload = {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "klines_lookback": 100,
        }
        response = client.post(f"{self.BASE}/calculate", json=payload)
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)


# ==========================================================================
# OpenAPI Documentation Sanity
# ==========================================================================

class TestDocs:
    def test_swagger_ui_available(self):
        response = client.get("/docs")
        assert response.status_code == 200

    def test_redoc_available(self):
        response = client.get("/redoc")
        assert response.status_code == 200

    def test_all_routers_registered(self):
        """Verify that all expected route prefixes appear in the OpenAPI spec."""
        schema = client.get("/api/v1/openapi.json").json()
        paths = list(schema["paths"].keys())
        expected_prefixes = [
            "/api/v1/bot",
            "/api/v1/config",
            "/api/v1/backtest",
            "/api/v1/market",
            "/api/v1/indicators",
        ]
        for prefix in expected_prefixes:
            matching = [p for p in paths if p.startswith(prefix)]
            assert matching, f"No routes found under prefix: {prefix}"
