import time
import pytest
from unittest.mock import MagicMock
from app.trading_engine.websocket_manager import BinanceFuturesWebSocketManager


def test_ws_manager_initialization():
    mock_client = MagicMock()
    manager = BinanceFuturesWebSocketManager(
        client=mock_client,
        symbol="BTCUSDT",
        interval="12h",
        testnet=True,
    )
    assert manager.symbol == "BTCUSDT"
    assert manager.interval == "12h"
    assert manager.testnet is True
    assert manager.get_position_amt() is None
    assert manager.get_available_balance() is None
    assert manager.get_mark_price() is None


def test_ws_account_update_handling():
    mock_client = MagicMock()
    manager = BinanceFuturesWebSocketManager(
        client=mock_client,
        symbol="BTCUSDT",
        interval="12h",
        testnet=True,
    )

    account_update_event = {
        "e": "ACCOUNT_UPDATE",
        "a": {
            "B": [
                {"a": "USDT", "wb": "1250.75", "cw": "1250.75"}
            ],
            "P": [
                {"s": "BTCUSDT", "pa": "0.15", "ep": "50000.0"},
                {"s": "ETHUSDT", "pa": "1.0", "ep": "3000.0"}
            ]
        }
    }

    manager._handle_user_data_event(account_update_event)

    assert manager.get_position_amt() == 0.15
    assert manager.get_position_entry_price() == 50000.0
    assert manager.get_available_balance() == 1250.75


def test_ws_order_trade_update_handling():
    mock_client = MagicMock()
    manager = BinanceFuturesWebSocketManager(
        client=mock_client,
        symbol="BTCUSDT",
        interval="12h",
        testnet=True,
    )

    order_event = {
        "e": "ORDER_TRADE_UPDATE",
        "o": {
            "s": "BTCUSDT",
            "i": 12345678,
            "c": "haqbot_test_1",
            "X": "FILLED",
            "p": "50000.0",
            "sp": "0.0",
            "ap": "50000.0",
            "q": "0.1",
            "z": "0.1",
            "o": "LIMIT",
            "S": "BUY",
        }
    }

    manager._handle_user_data_event(order_event)

    status_by_id = manager.get_order_status(12345678)
    assert status_by_id is not None
    assert status_by_id["status"] == "FILLED"
    assert status_by_id["executedQty"] == 0.1

    status_by_client_id = manager.get_order_status("haqbot_test_1")
    assert status_by_client_id is not None
    assert status_by_client_id["orderId"] == 12345678


def test_ws_market_data_event_handling():
    mock_client = MagicMock()
    manager = BinanceFuturesWebSocketManager(
        client=mock_client,
        symbol="BTCUSDT",
        interval="12h",
        testnet=True,
    )

    mark_price_event = {
        "e": "markPriceUpdate",
        "p": "50550.25"
    }

    manager._handle_market_data_event(mark_price_event)
    assert manager.get_mark_price() == 50550.25

    kline_event = {
        "e": "kline",
        "k": {
            "c": "50600.0",
            "x": True
        }
    }

    manager._handle_market_data_event(kline_event)
    assert manager.get_mark_price() == 50600.0


def test_ws_snapshot_update_and_fallback():
    mock_client = MagicMock()
    manager = BinanceFuturesWebSocketManager(
        client=mock_client,
        symbol="BTCUSDT",
        interval="12h",
        testnet=True,
    )

    manager.update_snapshot(position_amt=0.5, entry_price=48000.0, available_balance=2000.0, mark_price=49000.0)

    assert manager.get_position_amt() == 0.5
    assert manager.get_position_entry_price() == 48000.0
    assert manager.get_available_balance() == 2000.0
    assert manager.get_mark_price() == 49000.0


def test_ws_entry_price_staleness_timeout(monkeypatch):
    """Entry price older than 30s should return None to force REST fallback."""
    mock_client = MagicMock()
    manager = BinanceFuturesWebSocketManager(
        client=mock_client,
        symbol="BTCUSDT",
        interval="12h",
        testnet=True,
    )

    # Set entry price with a recent timestamp
    current_time = time.time()
    manager.update_snapshot(entry_price=50000.0)

    # Should return the cached value when fresh
    assert manager.get_position_entry_price() == 50000.0

    # Simulate time passing beyond 30s threshold
    monkeypatch.setattr(time, "time", lambda: current_time + 31.0)
    # Should return None now (stale)
    assert manager.get_position_entry_price() is None


def test_ws_entry_price_time_updated_on_account_update():
    """_entry_price_time should be set when ACCOUNT_UPDATE arrives."""
    mock_client = MagicMock()
    manager = BinanceFuturesWebSocketManager(
        client=mock_client,
        symbol="BTCUSDT",
        interval="12h",
        testnet=True,
    )

    assert manager._entry_price_time == 0.0

    account_update_event = {
        "e": "ACCOUNT_UPDATE",
        "a": {
            "B": [],
            "P": [
                {"s": "BTCUSDT", "pa": "0.1", "ep": "48000.0"}
            ]
        }
    }

    manager._handle_user_data_event(account_update_event)
    assert manager._entry_price_time > 0.0
    assert manager.get_position_entry_price() == 48000.0


def test_ws_entry_price_time_updated_on_snapshot():
    """_entry_price_time should be set when update_snapshot sets entry_price."""
    mock_client = MagicMock()
    manager = BinanceFuturesWebSocketManager(
        client=mock_client,
        symbol="BTCUSDT",
        interval="12h",
        testnet=True,
    )

    assert manager._entry_price_time == 0.0

    manager.update_snapshot(entry_price=52000.0)
    assert manager._entry_price_time > 0.0
    assert manager.get_position_entry_price() == 52000.0


def test_ws_entry_price_time_not_updated_without_entry_price():
    """_entry_price_time should NOT change if update_snapshot doesn't include entry_price."""
    mock_client = MagicMock()
    manager = BinanceFuturesWebSocketManager(
        client=mock_client,
        symbol="BTCUSDT",
        interval="12h",
        testnet=True,
    )

    assert manager._entry_price_time == 0.0

    # Update only mark price, not entry price
    manager.update_snapshot(mark_price=49000.0)
    assert manager._entry_price_time == 0.0
