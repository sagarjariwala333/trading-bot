import pytest

from app.trading_engine.bot import ExchangeGateway, TradingBot


class DummyLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def debug(self, *args, **kwargs):
        pass


def test_extract_order_ref_prefers_order_id():
    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.log = DummyLogger()

    response = {"orderId": 12345, "clientOrderId": "abc"}

    assert gateway._extract_order_ref(response) == (12345, "order")


def test_extract_order_ref_falls_back_to_algo_id():
    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.log = DummyLogger()

    response = {"algoId": 67890, "clientAlgoId": "xyz", "algoType": "CONDITIONAL"}

    assert gateway._extract_order_ref(response) == (67890, "algo")


def test_validate_sl_price_rejects_immediate_long_trigger():
    bot = TradingBot.__new__(TradingBot)
    bot.log = DummyLogger()
    bot.ex = type("Ex", (), {"round_price": lambda self, price: str(price), "get_current_price": lambda self: 100.0})()

    is_valid, adjusted_price, reason = bot.validate_sl_price("LONG", 100.0, 100.0)

    assert is_valid is False
    assert adjusted_price == 100.0
    assert "immediately trigger" in reason.lower()


def test_validate_sl_price_rounds_to_tick_size_for_short():
    bot = TradingBot.__new__(TradingBot)
    bot.log = DummyLogger()
    bot.ex = type("Ex", (), {"round_price": lambda self, price: "100.10", "get_current_price": lambda self: 100.0})()

    is_valid, adjusted_price, reason = bot.validate_sl_price("SHORT", 100.104, 100.0)

    assert is_valid is True
    assert adjusted_price == 100.10
    assert reason is None


def test_call_does_not_retry_non_retryable_binance_errors():
    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.log = DummyLogger()
    gateway.cfg = type("Cfg", (), {"symbol": "BTCUSDT"})()

    class DummyError(Exception):
        code = -2011

    calls = {"count": 0}

    def fail(*args, **kwargs):
        calls["count"] += 1
        raise DummyError("Unknown order sent")

    with pytest.raises(DummyError):
        gateway._call(fail)

    assert calls["count"] == 1
