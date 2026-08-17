import pytest
from app.trading_engine.bot import (
    sl_price_for_tp_level, tp_ladder_price, next_tp_price_and_qty,
    TradingBot, parse_bool
)


class DummyLogger:
    def info(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): pass
    def critical(self, *args, **kwargs): pass
    def debug(self, *args, **kwargs): pass


def test_short_position_sl_tp_price_calculation():
    entry = 63220.45
    atr = 39.10
    direction = "SHORT"
    custom_levels = [0.5]
    step = 0.5
    sl_multiple = 1.0

    # Level 0 Initial Stop Loss for SHORT must be ABOVE entry price
    sl_0 = sl_price_for_tp_level(entry, atr, direction, 0, custom_levels, step, sl_multiple=sl_multiple)
    assert sl_0 == pytest.approx(63259.55, abs=0.01)
    assert sl_0 > entry

    # Level 1 Take Profit for SHORT must be BELOW entry price
    tp_1 = tp_ladder_price(entry, atr, direction, 1, custom_levels, step)
    assert tp_1 == pytest.approx(63200.90, abs=0.01)
    assert tp_1 < entry


def test_long_position_sl_tp_price_calculation():
    entry = 60000.00
    atr = 500.0
    direction = "LONG"
    custom_levels = [0.5]
    step = 0.5
    sl_multiple = 1.0

    # Level 0 Initial Stop Loss for LONG must be BELOW entry price
    sl_0 = sl_price_for_tp_level(entry, atr, direction, 0, custom_levels, step, sl_multiple=sl_multiple)
    assert sl_0 == 59500.0
    assert sl_0 < entry

    # Level 1 Take Profit for LONG must be ABOVE entry price
    tp_1 = tp_ladder_price(entry, atr, direction, 1, custom_levels, step)
    assert tp_1 == 60250.0
    assert tp_1 > entry


def test_validate_sl_price_detects_short_breach():
    bot = TradingBot.__new__(TradingBot)
    bot.log = DummyLogger()
    bot.ex = type("Ex", (), {
        "round_price": lambda self, price: f"{price:.2f}",
        "get_current_price": lambda self: 63356.30
    })()

    # SL at 63259.55 when mark price is 63356.30 (mark price > SL for SHORT -> SL breached!)
    is_valid, adjusted_price, reason = bot.validate_sl_price("SHORT", 63259.55, 63356.30)
    assert is_valid is False
    assert adjusted_price <= 63356.30


def test_write_live_status_fallback_scanner_ignores_non_reduce_only_entry_orders():
    # Simulate open orders list containing an entry limit order (reduceOnly=False) and a TP order (reduceOnly=True)
    open_orders = [
        {"orderId": 101, "type": "LIMIT", "price": "63200.00", "origQty": "0.05", "reduceOnly": False},
        {"orderId": 102, "type": "LIMIT", "price": "63200.90", "origQty": "0.015", "reduceOnly": True},
        {"algoId": 201, "type": "STOP_MARKET", "stopPrice": "63259.55", "origQty": "0.05", "reduceOnly": True},
    ]

    snapshot = {"sl_price": None, "sl_qty": None, "tp_price": None, "tp_qty": None}

    # Simulate fallback scanner logic
    for o in open_orders:
        otype = str(o.get("type") or o.get("orderType") or o.get("algoType") or "").upper()
        stop_p = float(o.get("triggerPrice") or o.get("stopPrice") or 0)
        limit_p = float(o.get("price", 0) or 0)
        qty = float(o.get("origQty") or o.get("quantity") or 0)
        is_reduce = parse_bool(o.get("reduceOnly"))

        if snapshot["sl_price"] is None and is_reduce and (otype in ("STOP_MARKET", "STOP", "STOP_LOSS", "STOP_LOSS_LIMIT", "TRAILING_STOP_MARKET", "CONDITIONAL") or stop_p > 0):
            snapshot["sl_price"] = stop_p if stop_p > 0 else limit_p
            snapshot["sl_qty"] = qty
        elif snapshot["tp_price"] is None and is_reduce and (otype in ("LIMIT", "TAKE_PROFIT", "TAKE_PROFIT_MARKET")):
            snapshot["tp_price"] = limit_p if limit_p > 0 else stop_p
            snapshot["tp_qty"] = qty

    # Verify that the non-reduceOnly Entry 2 order (63200.00) was NOT taken as SL!
    assert snapshot["sl_price"] == 63259.55
    assert snapshot["tp_price"] == 63200.90
