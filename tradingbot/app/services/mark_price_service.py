"""Lightweight service for fetching current Binance Futures mark price.

Uses a background thread that polls Binance's public REST API every 1 second.
The latest mark price is stored in-memory and read instantly (zero-cost) by the
dashboard WebSocket endpoint on each tick.

Why REST polling instead of Binance WebSocket stream:
  - Binance's ``@markPrice`` WS stream can be blocked by certain firewalls/proxies.
  - The REST endpoint (``fapi/v1/premiumIndex``) is more reliably accessible.
  - At 1 request/second with weight=1, we use only ~60/2400 of the rate limit per minute.
  - The background thread means the dashboard WS endpoint never blocks on a network call.
"""

import logging
import threading
import time
from typing import Optional, Dict, Any

import requests

logger = logging.getLogger("ha_alma_bot")

# Binance public endpoint — no API key required
_PREMIUM_INDEX_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"

# In-memory store: {symbol: {"mark_price": float, "updated_at": float}}
_latest: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()

# Active background pollers: {symbol: threading.Thread}
_pollers: Dict[str, threading.Thread] = {}

# How often the background thread fetches a new price (seconds)
POLL_INTERVAL_SECONDS = 5

# How old (seconds) a cached price can be before we consider it stale
STALE_THRESHOLD_SECONDS = 15


def _poll_loop(symbol: str):
    """Background thread: continuously fetch mark price from Binance REST API."""
    logger.info(f"[MarkPrice] Started background poller for {symbol} (every {POLL_INTERVAL_SECONDS}s)")

    consecutive_failures = 0

    while True:
        try:
            resp = requests.get(
                _PREMIUM_INDEX_URL,
                params={"symbol": symbol},
                timeout=5,
            )
            if resp.status_code in (429, 418):
                logger.warning(f"[MarkPrice] Binance rate limit hit ({resp.status_code}) for {symbol}. Backing off 60s...")
                time.sleep(60)
                continue
            resp.raise_for_status()
            data = resp.json()
            mark_price = float(data["markPrice"])

            if mark_price > 0:
                with _lock:
                    _latest[symbol] = {
                        "mark_price": mark_price,
                        "updated_at": time.time(),
                    }
                if consecutive_failures > 0:
                    logger.info(f"[MarkPrice] Recovered for {symbol} after {consecutive_failures} failures")
                consecutive_failures = 0

        except Exception as e:
            consecutive_failures += 1
            err_str = str(e)
            if "-1003" in err_str or "banned" in err_str.lower() or "429" in err_str:
                logger.warning(f"[MarkPrice] IP banned / rate limited (-1003) for {symbol}: {e}. Backing off 60s...")
                time.sleep(60)
            else:
                if consecutive_failures <= 3 or consecutive_failures % 10 == 0:
                    logger.warning(f"[MarkPrice] Fetch failed for {symbol} (attempt {consecutive_failures}): {e}")

        time.sleep(POLL_INTERVAL_SECONDS)


def ensure_subscribed(symbol: str = "BTCUSDT"):
    """Start the background polling thread for *symbol* if not already running."""
    symbol = symbol.upper()
    if symbol in _pollers and _pollers[symbol].is_alive():
        return  # Already polling

    t = threading.Thread(target=_poll_loop, args=(symbol,), daemon=True, name=f"markprice-{symbol}")
    t.start()
    _pollers[symbol] = t


def fetch_direct(symbol: str) -> Optional[float]:
    """Perform a direct REST fetch for mark price."""
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
    """Return the latest mark price for *symbol*, or ``None`` if unavailable.

    This is a non-blocking read from in-memory — no network call.
    The background thread keeps the value fresh (~1s old at most).
    """
    symbol = symbol.upper()

    # Auto-subscribe on first access
    ensure_subscribed(symbol)

    with _lock:
        entry = _latest.get(symbol)

    if not entry:
        # Immediate fallback for the very first read
        return fetch_direct(symbol)

    return entry["mark_price"]


def get_mark_price_updated_at(symbol: str = "BTCUSDT") -> Optional[float]:
    """Return the epoch timestamp of the last mark price update, or ``None``."""
    symbol = symbol.upper()
    with _lock:
        entry = _latest.get(symbol)
    return entry["updated_at"] if entry else None


def is_price_stale(symbol: str = "BTCUSDT") -> bool:
    """Return True if the mark price hasn't been updated recently."""
    symbol = symbol.upper()
    with _lock:
        entry = _latest.get(symbol)
    if not entry:
        return True
    return (time.time() - entry["updated_at"]) > STALE_THRESHOLD_SECONDS
