"""
Temporary Binance REST instrumentation for rate-limit investigation.

Python automatically imports sitecustomize when this directory is on PYTHONPATH.
BotManager already sets PYTHONPATH to the tradingbot project root for the bot
subprocess, so this lets us measure actual Binance REST calls without changing
trading-engine behavior.

This file is intentionally diagnostic only: it does not throttle, retry, or
change any Binance request.
"""

import functools
import inspect
import logging
import os
import threading
import time
from collections import Counter, deque


_LOG = logging.getLogger("binance_rest_monitor")
_LOCK = threading.Lock()
_CALL_TIMES = deque()
_COUNTS = Counter()
_TOTAL = 0
_LAST_SUMMARY = 0.0
_PATCHED = False


def _caller_name():
    """Return the first useful caller outside this monitor wrapper."""
    try:
        for frame in inspect.stack()[2:8]:
            module = frame.frame.f_globals.get("__name__", "")
            if module != __name__:
                return f"{module}.{frame.function}"
    except Exception:
        pass
    return "unknown"


def _prune(now):
    cutoff = now - 60.0
    while _CALL_TIMES and _CALL_TIMES[0] < cutoff:
        _CALL_TIMES.popleft()


def _record(endpoint, success, elapsed_ms, caller, kwargs):
    global _TOTAL, _LAST_SUMMARY
    now = time.time()
    with _LOCK:
        _CALL_TIMES.append(now)
        _COUNTS[endpoint] += 1
        _TOTAL += 1
        _prune(now)
        rolling = len(_CALL_TIMES)

        # Log every request only while traffic is already suspiciously high.
        # This keeps normal logs manageable while making a runaway loop obvious.
        if rolling >= 100:
            _LOG.warning(
                "[BINANCE_REST_HIGH_RATE] pid=%s endpoint=%s caller=%s "
                "rolling_60s=%d total=%d success=%s elapsed_ms=%.1f",
                os.getpid(), endpoint, caller, rolling, _TOTAL, success, elapsed_ms,
            )

        # Emit a complete endpoint breakdown approximately once per minute.
        if now - _LAST_SUMMARY >= 60.0:
            _LAST_SUMMARY = now
            breakdown = ", ".join(
                f"{name}={count}" for name, count in _COUNTS.most_common()
            ) or "none"
            _LOG.warning(
                "[BINANCE_REST_SUMMARY] pid=%s rolling_60s=%d total_since_start=%d "
                "endpoints={%s}",
                os.getpid(), rolling, _TOTAL, breakdown,
            )


def _wrap_method(name, original):
    @functools.wraps(original)
    def wrapped(*args, **kwargs):
        start = time.monotonic()
        caller = _caller_name()
        success = False
        try:
            result = original(*args, **kwargs)
            success = True
            return result
        finally:
            elapsed_ms = (time.monotonic() - start) * 1000.0
            _record(name, success, elapsed_ms, caller, kwargs)

    return wrapped


def _patch_binance():
    global _PATCHED
    if _PATCHED:
        return
    try:
        from binance.client import Client
    except Exception:
        # The web/API process may start before dependencies are available in some
        # environments. Never allow diagnostics to prevent the application starting.
        return

    for name in dir(Client):
        if not name.startswith("futures_"):
            continue
        try:
            original = getattr(Client, name)
            if not callable(original) or getattr(original, "_rest_monitor_wrapped", False):
                continue
            wrapped = _wrap_method(name, original)
            wrapped._rest_monitor_wrapped = True
            setattr(Client, name, wrapped)
        except Exception:
            continue

    _PATCHED = True
    _LOG.warning(
        "[BINANCE_REST_MONITOR] enabled pid=%s branch=debug/rate-limit-investigation",
        os.getpid(),
    )


_patch_binance()
