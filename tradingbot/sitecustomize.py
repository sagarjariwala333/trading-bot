"""
Temporary Binance REST instrumentation for rate-limit investigation.

This module is loaded automatically by Python when the application root is on
sys.path. It is also safe to import explicitly if a runtime does not auto-load
sitecustomize.

Diagnostic only: it does not throttle, retry, or change Binance requests.
"""

import functools
import inspect
import logging
import os
import threading
import time
from collections import Counter, deque

print(
    f"[BINANCE_REST_MONITOR_BOOT] pid={os.getpid()} cwd={os.getcwd()}",
    flush=True,
)

_LOG = logging.getLogger("binance_rest_monitor")
_LOCK = threading.Lock()
_CALL_TIMES = deque()
_COUNTS = Counter()
_TOTAL = 0
_LAST_SUMMARY = 0.0
_PATCHED = False


def _caller_name():
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


def _record(endpoint, success, elapsed_ms, caller):
    global _TOTAL, _LAST_SUMMARY
    now = time.time()
    with _LOCK:
        _CALL_TIMES.append(now)
        _COUNTS[endpoint] += 1
        _TOTAL += 1
        _prune(now)
        rolling = len(_CALL_TIMES)

        if rolling >= 100:
            _LOG.warning(
                "[BINANCE_REST_HIGH_RATE] pid=%s endpoint=%s caller=%s "
                "rolling_60s=%d total=%d success=%s elapsed_ms=%.1f",
                os.getpid(), endpoint, caller, rolling, _TOTAL, success, elapsed_ms,
            )

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
            _record(name, success, elapsed_ms, caller)

    wrapped._rest_monitor_wrapped = True
    return wrapped


def install_binance_rest_monitor():
    """Patch python-binance Futures REST methods once and report installation."""
    global _PATCHED
    if _PATCHED:
        return True

    try:
        from binance.client import Client
    except Exception as exc:
        print(
            f"[BINANCE_REST_MONITOR_ERROR] cannot import binance.client: {exc!r}",
            flush=True,
        )
        return False

    patched = 0
    for name in dir(Client):
        if not name.startswith("futures_"):
            continue
        try:
            original = getattr(Client, name)
            if not callable(original) or getattr(original, "_rest_monitor_wrapped", False):
                continue
            setattr(Client, name, _wrap_method(name, original))
            patched += 1
        except Exception as exc:
            print(
                f"[BINANCE_REST_MONITOR_ERROR] failed to patch {name}: {exc!r}",
                flush=True,
            )

    _PATCHED = True
    print(
        f"[BINANCE_REST_MONITOR_ENABLED] pid={os.getpid()} patched_methods={patched}",
        flush=True,
    )
    return True


# Normal Python sitecustomize path.
install_binance_rest_monitor()
