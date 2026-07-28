import os
import pytest
from app.core.db import (
    init_db, save_db_live_status, get_db_live_status,
    record_db_order, update_db_order_status, get_db_orders,
    record_db_trade, get_db_trades, get_db_trade_summary,
    record_db_signal, get_db_signals,
    insert_db_log, get_db_logs
)

def test_db_initialization_and_helpers():
    init_db()
    symbol = "TESTUSDT"

    # 1. Test live status
    save_db_live_status(symbol, {"mark_price": 65000.0, "status": "IN_POSITION"})
    status = get_db_live_status(symbol)
    assert status.get("mark_price") == 65000.0

    # 2. Test order recording & update
    record_db_order(symbol, {
        "trade_id": "test_trade_1",
        "order_id": "123456",
        "algo_id": "999999",
        "client_order_id": "haqbot_123456",
        "side": "BUY",
        "order_type": "LIMIT",
        "purpose": "ENTRY_1",
        "price": 64500.0,
        "quantity": 0.1,
        "status": "NEW"
    })
    orders = get_db_orders(symbol, limit=10)
    assert len(orders) >= 1
    assert orders[0]["order_id"] == "123456"

    update_db_order_status("123456", "FILLED", executed_qty=0.1)
    orders_updated = get_db_orders(symbol, limit=10)
    assert orders_updated[0]["status"] == "FILLED"

    # 3. Test trade recording & summary
    record_db_trade(symbol, {
        "trade_id": "test_trade_1",
        "direction": "LONG",
        "entry_price": 64500.0,
        "exit_price": 65500.0,
        "quantity": 0.1,
        "leverage": 10,
        "margin_used": 645.0,
        "gross_pnl": 100.0,
        "estimated_fees": 4.5,
        "realized_pnl": 95.5,
        "return_pct": 14.8,
        "close_reason": "TP_COMPLETED"
    })
    trades = get_db_trades(symbol, limit=10)
    assert len(trades) >= 1
    assert trades[0]["realized_pnl"] == 95.5

    summary = get_db_trade_summary(symbol)
    assert summary["total_trades"] >= 1
    assert summary["wins"] >= 1

    # 4. Test signal recording
    record_db_signal(symbol, {
        "candle_time": "2026-07-29T00:00:00",
        "ha_open": 64000.0,
        "ha_close": 64500.0,
        "alma": 64200.0,
        "rsi": 62.5,
        "rsi_sma": 55.0,
        "atr": 200.0,
        "signal": "LONG",
        "decision": "OPEN_LONG",
        "executed": True
    })
    signals = get_db_signals(symbol, limit=10)
    assert len(signals) >= 1
    assert signals[0]["signal"] == "LONG"

    # 5. Test log recording
    insert_db_log(symbol, "INFO", "Test log message for full DB integration")
    logs = get_db_logs(symbol, limit=10)
    assert len(logs) >= 1
    assert "Test log message for full DB integration" in logs[-1]
