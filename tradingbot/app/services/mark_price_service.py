"""Real-time Binance Futures mark price via ThreadedWebsocketManager.

Maintains a persistent, auto-reconnecting WebSocket connection to Binance Futures.
Updates arrive in real time (every ~1s) with ZERO REST API weight usage, completely
eliminating rate-limit / IP-ban (-1003) risks.

The latest mark price is stored in-memory and read instantly (zero-cost) by the
dashboard WebSocket endpoint on each tick.
"""

import logging
import threading
import time
from typing import Optional, Dict, Any

from binance import ThreadedWebsocketManager

logger = logging.getLogger("ha_alma_bot")

# In-memory store: {symbol: {"mark_price": float, "updated_at": float}}
_latest: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()

# Global ThreadedWebsocketManager instance
_twm: Optional[ThreadedWebsocketManager] = None
_twm_lock = threading.Lock()
_subscribed_symbols: set = set()

# How old (seconds) a cached price can be before we consider it stale
STALE_THRESHOLD_SECONDS = 15


def _handle_socket_message(msg: dict):
    """Callback for Binance WebSocket mark price updates."""
    try:
        data = msg.get("data", {})
        if not data:
            data = msg  # Direct payload format fallback

        symbol = data.get("s")
        price_str = data.get("p")

        if symbol and price_str:
            mark_price = float(price_str)
            if mark_price > 0:
                with _lock:
                    _latest[symbol.upper()] = {
                        "mark_price": mark_price,
                        "updated_at": time.time(),
                    }
    except Exception as e:
        logger.warning(f"[MarkPriceWS] Error processing WebSocket message: {e}")


def _init_twm():
    """Initialize and start the global ThreadedWebsocketManager."""
    global _twm
    with _twm_lock:
        if _twm is None:
            try:
                logger.info("[MarkPriceWS] Starting Binance Futures WebSocket Manager...")
                _twm = ThreadedWebsocketManager()
                _twm.start()
                logger.info("[MarkPriceWS] WebSocket Manager started successfully.")
            except Exception as e:
                logger.error(f"[MarkPriceWS] Failed to start WebSocket Manager: {e}")
                _twm = None


def ensure_subscribed(symbol: str = "BTCUSDT"):
    """Subscribe to Binance Futures WebSocket mark price stream for *symbol*."""
    symbol = symbol.upper()
    
    with _twm_lock:
        if symbol in _subscribed_symbols:
            return  # Already subscribed

        if _twm is None:
            _init_twm()

        if _twm is not None:
            try:
                logger.info(f"[MarkPriceWS] Subscribing to Futures Mark Price WebSocket for {symbol}...")
                _twm.start_symbol_mark_price_socket(
                    callback=_handle_socket_message,
                    symbol=symbol,
                    fast=True,  # 1-second update interval
                )
                _subscribed_symbols.add(symbol)
                logger.info(f"[MarkPriceWS] Subscribed successfully to {symbol} WebSocket stream.")
            except Exception as e:
                logger.error(f"[MarkPriceWS] Error subscribing to {symbol}: {e}")


import requests

# Binance public REST endpoint — used ONLY as a 1-time fallback on initial load
_PREMIUM_INDEX_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"


def fetch_direct(symbol: str) -> Optional[float]:
    """Perform a 1-time REST fetch as fallback while waiting for the first WS packet."""
    try:
        resp = requests.get(_PREMIUM_INDEX_URL, params={"symbol": symbol}, timeout=5)
        resp.raise_for_status()
        price = float(resp.json()["markPrice"])
        if price > 0:
            with _lock:
                _latest[symbol] = {"mark_price": price, "updated_at": time.time()}
            return price
    except Exception:
        pass
    return None


def get_mark_price(symbol: str = "BTCUSDT") -> Optional[float]:
    """Return the latest mark price for *symbol* from the WebSocket stream.

    Non-blocking read from in-memory — zero network overhead.
    """
    symbol = symbol.upper()
    ensure_subscribed(symbol)

    with _lock:
        entry = _latest.get(symbol)

    if not entry:
        return fetch_direct(symbol)

    return entry["mark_price"]


def get_mark_price_updated_at(symbol: str = "BTCUSDT") -> Optional[float]:
    """Return the epoch timestamp of the last WebSocket mark price update, or ``None``."""
    symbol = symbol.upper()
    with _lock:
        entry = _latest.get(symbol)
    return entry["updated_at"] if entry else None


def is_price_stale(symbol: str = "BTCUSDT") -> bool:
    """Return True if the WebSocket mark price hasn't been updated recently."""
    symbol = symbol.upper()
    with _lock:
        entry = _latest.get(symbol)
    if not entry:
        return True
    return (time.time() - entry["updated_at"]) > STALE_THRESHOLD_SECONDS
