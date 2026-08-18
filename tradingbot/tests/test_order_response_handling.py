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


def test_call_parses_ip_ban_timestamp_and_sleeps(monkeypatch):
    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.log = DummyLogger()
    gateway.cfg = type("Cfg", (), {"symbol": "BTCUSDT"})()

    slept = []
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))

    class RateLimitBanError(Exception):
        code = -1003

    future_ban_ms = int((1000000000.0 + 3600) * 1000)
    monkeypatch.setattr("time.time", lambda: 1000000000.0)

    attempts = {"count": 0}

    def fn():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RateLimitBanError(f"APIError(code=-1003): Way too many requests; IP(1.2.3.4) banned until {future_ban_ms}.")
        return {"status": "FILLED"}

    res = gateway._call(fn, retries=2)
    assert res == {"status": "FILLED"}
    assert attempts["count"] == 2
    assert len(slept) == 1
    assert slept[0] >= 3601.5  # 3600s + 2s buffer


def test_get_order_status_uses_call_retry(monkeypatch):
    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.log = DummyLogger()
    gateway.cfg = type("Cfg", (), {"symbol": "BTCUSDT"})()

    calls = []

    def mock_call(fn, *args, **kwargs):
        calls.append(fn)
        return {"orderId": 123, "status": "NEW"}

    gateway._call = mock_call
    gateway.client = type("Client", (), {"futures_get_order": lambda self, symbol, orderId: None})()

    res = gateway.get_order_status(123)
    assert res == {"orderId": 123, "status": "NEW"}
    assert len(calls) == 1


def test_position_info_caching_deduplicates_calls(monkeypatch):
    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.log = DummyLogger()
    gateway.cfg = type("Cfg", (), {"symbol": "BTCUSDT"})()
    gateway._pos_info_cache = None
    gateway._pos_info_time = 0.0

    call_count = {"count": 0}

    def mock_call(fn, *args, **kwargs):
        call_count["count"] += 1
        return [{"symbol": "BTCUSDT", "positionAmt": "1.5", "entryPrice": "50000.0"}]

    gateway._call = mock_call
    gateway.client = type("Client", (), {"futures_position_information": lambda self, symbol: None})()

    # First query -> triggers API call
    amt1 = gateway.get_position_amt()
    price1 = gateway.get_position_entry_price()

    assert amt1 == 1.5
    assert price1 == 50000.0
    assert call_count["count"] == 1  # Exactly 1 API call for both amt and entry price

    # Invalidate cache
    gateway.clear_cache()
    amt2 = gateway.get_position_amt()
    assert amt2 == 1.5
    assert call_count["count"] == 2


def test_entry_price_zero_guard_forces_fresh_fetch():
    """If position exists (positionAmt != 0) but entry price is 0.0,
    get_position_entry_price must force a fresh REST call."""
    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.log = DummyLogger()
    gateway.cfg = type("Cfg", (), {"symbol": "BTCUSDT"})()
    gateway._pos_info_cache = None
    gateway._pos_info_time = 0.0
    gateway.ws_manager = None

    call_count = {"count": 0}

    def mock_call(fn, *args, **kwargs):
        call_count["count"] += 1
        if call_count["count"] == 1:
            # First call returns stale entry price of 0.0 with an open position
            return [{"symbol": "BTCUSDT", "positionAmt": "0.5", "entryPrice": "0.0"}]
        else:
            # Second call (force_fresh) returns the real entry price
            return [{"symbol": "BTCUSDT", "positionAmt": "0.5", "entryPrice": "50000.0"}]

    gateway._call = mock_call
    gateway.client = type("Client", (), {"futures_position_information": lambda self, symbol: None})()

    price = gateway.get_position_entry_price()
    assert price == 50000.0
    assert call_count["count"] == 2  # First stale, second forced fresh


def test_entry_price_zero_guard_no_retry_when_flat():
    """If positionAmt is 0, entry price 0.0 is expected - no retry."""
    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.log = DummyLogger()
    gateway.cfg = type("Cfg", (), {"symbol": "BTCUSDT"})()
    gateway._pos_info_cache = None
    gateway._pos_info_time = 0.0
    gateway.ws_manager = None

    call_count = {"count": 0}

    def mock_call(fn, *args, **kwargs):
        call_count["count"] += 1
        return [{"symbol": "BTCUSDT", "positionAmt": "0.0", "entryPrice": "0.0"}]

    gateway._call = mock_call
    gateway.client = type("Client", (), {"futures_position_information": lambda self, symbol: None})()

    price = gateway.get_position_entry_price()
    assert price == 0.0
    assert call_count["count"] == 1  # Only one call, no retry


def test_last_entry_price_tracking_in_bot_state():
    """BotState.last_entry_price should persist through saves and reset on reset()."""
    from app.trading_engine.bot import BotState

    state = BotState()
    assert state.last_entry_price is None

    state.last_entry_price = 50000.0
    assert state.last_entry_price == 50000.0

    state.reset()
    assert state.last_entry_price is None
