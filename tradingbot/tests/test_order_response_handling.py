import pytest

from app.trading_engine.bot import ExchangeGateway


class DummyLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
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
