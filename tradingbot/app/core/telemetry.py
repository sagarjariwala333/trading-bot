import os
import sys
import logging
import functools
import inspect
import threading
import time
from collections import Counter, deque
from typing import Any, Dict, Optional, Callable
from app.core.config import settings

logger = logging.getLogger("telemetry")

_langfuse_client = None
_langfuse_enabled = False


def init_telemetry():
    global _langfuse_client, _langfuse_enabled

    public_key = getattr(settings, "LANGFUSE_PUBLIC_KEY", "") or os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    secret_key = getattr(settings, "LANGFUSE_SECRET_KEY", "") or os.environ.get("LANGFUSE_SECRET_KEY", "")
    host = getattr(settings, "LANGFUSE_HOST", "https://cloud.langfuse.com") or os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
    enabled = getattr(settings, "LANGFUSE_ENABLED", True)

    if not enabled:
        logger.info("Langfuse telemetry disabled by configuration.")
        _langfuse_enabled = False
        return None

    if not public_key or not secret_key:
        logger.warning("Langfuse public/secret keys not set. Telemetry will operate in silent fallback mode.")
        _langfuse_enabled = False
        return None

    os.environ["LANGFUSE_PUBLIC_KEY"] = public_key
    os.environ["LANGFUSE_SECRET_KEY"] = secret_key
    os.environ["LANGFUSE_HOST"] = host
    os.environ["LANGFUSE_BASE_URL"] = host

    try:
        from langfuse import Langfuse
        _langfuse_client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host
        )
        _langfuse_enabled = True
        logger.info(f"Langfuse telemetry initialized successfully (host: {host}).")
        return _langfuse_client
    except Exception as e:
        logger.error(f"Failed to initialize Langfuse telemetry client: {e}")
        _langfuse_enabled = False
        return None


def get_langfuse_client():
    global _langfuse_client
    if _langfuse_client is None:
        init_telemetry()
    return _langfuse_client


class LangfuseLoggingHandler(logging.Handler):
    """
    Custom logging handler that routes Python standard logging records
    (logger.info, logger.warning, logger.error) into Langfuse events/observations.
    """
    def __init__(self, level=logging.NOTSET):
        super().__init__(level)

    def emit(self, record: logging.LogRecord):
        if not _langfuse_enabled:
            return
        client = get_langfuse_client()
        if not client:
            return

        try:
            msg = self.format(record)
            level = record.levelname
            metadata = {
                "logger": record.name,
                "filename": record.filename,
                "lineno": record.lineno,
                "funcName": record.funcName,
                "process": record.process,
                "thread": record.threadName,
            }
            if record.exc_info:
                metadata["exc_info"] = self.formatException(record.exc_info)

            client.create_event(
                name=f"Log {level}: {record.name}",
                input={"message": msg},
                level="ERROR" if level in ("ERROR", "CRITICAL") else ("WARNING" if level == "WARNING" else "DEFAULT"),
                metadata=metadata
            )
        except Exception:
            pass


def observe_trace(name: Optional[str] = None, as_type: Optional[str] = None):
    """Decorator to wrap functions as a Langfuse trace/span with safe exception handling."""
    def decorator(func: Callable):
        try:
            from langfuse import observe
            kwargs = {}
            if name:
                kwargs["name"] = name
            if as_type and as_type != "trace":
                kwargs["as_type"] = as_type
            observed_func = observe(**kwargs)(func)
        except Exception:
            observed_func = func

        @functools.wraps(func)
        def wrapper(*args, **kwargs_fn):
            if not _langfuse_enabled:
                return func(*args, **kwargs_fn)
            try:
                return observed_func(*args, **kwargs_fn)
            except Exception as e:
                trace_event(
                    name=f"Exception in {func.__name__}",
                    level="ERROR",
                    metadata={"error": str(e), "func": func.__name__}
                )
                raise e
        return wrapper
    return decorator


def trace_event(
    name: str,
    level: str = "DEFAULT",
    input: Optional[Any] = None,
    output: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[list] = None
):
    """Record an explicit domain event in Langfuse."""
    if not _langfuse_enabled:
        return
    client = get_langfuse_client()
    if not client:
        return

    try:
        client.create_event(
            name=name,
            level=level,
            input=input,
            output=output,
            metadata=metadata or {}
        )
    except Exception as e:
        logger.debug(f"Failed to send trace_event '{name}' to Langfuse: {e}")


def flush_telemetry():
    """Flush pending events on shutdown."""
    client = get_langfuse_client()
    if client:
        try:
            client.flush()
        except Exception:
            pass


# --------------------------------------------------------------------------
# TEMPORARY BINANCE REST RATE-LIMIT DIAGNOSTICS
# --------------------------------------------------------------------------
# Uses the existing Langfuse integration rather than stdout/sitecustomize.
# No Binance request is changed, throttled, retried, or suppressed.
# The monitor aggregates locally and emits one Langfuse event per minute so
# telemetry itself does not create one event for every Binance REST call.

_binance_monitor_lock = threading.Lock()
_binance_call_times = deque()
_binance_counts = Counter()
_binance_total = 0
_binance_last_summary = 0.0
_binance_last_call = {}
_binance_patched = False


def _binance_caller():
    try:
        for frame in inspect.stack()[3:10]:
            module = frame.frame.f_globals.get("__name__", "")
            if module not in (__name__, "binance.client"):
                return f"{module}.{frame.function}"
    except Exception:
        pass
    return "unknown"


def _emit_binance_summary(now: float, rolling_60s: int):
    global _binance_last_summary
    if now - _binance_last_summary < 60.0:
        return

    _binance_last_summary = now
    counts = dict(_binance_counts)
    top = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    trace_event(
        name="Binance REST Rate Summary",
        metadata={
            "pid": os.getpid(),
            "rolling_60s_requests": rolling_60s,
            "total_requests_since_start": _binance_total,
            "endpoint_counts": dict(top),
            "top_endpoint": top[0][0] if top else None,
            "top_endpoint_count": top[0][1] if top else 0,
        },
        input={"source": "python-binance Client Futures REST methods"},
    )


def _record_binance_call(endpoint: str, success: bool, elapsed_ms: float, caller: str):
    global _binance_total
    now = time.time()
    with _binance_monitor_lock:
        _binance_call_times.append(now)
        _binance_counts[endpoint] += 1
        _binance_total += 1
        previous = _binance_last_call.get(endpoint)
        interval_ms = (now - previous) * 1000.0 if previous else None
        _binance_last_call[endpoint] = now

        cutoff = now - 60.0
        while _binance_call_times and _binance_call_times[0] < cutoff:
            _binance_call_times.popleft()
        rolling = len(_binance_call_times)

        # Keep the high-rate event useful but bounded: one event per endpoint per
        # minute when that endpoint alone reaches 100 calls/minute.
        if rolling >= 100 and _binance_counts[endpoint] >= 100:
            trace_event(
                name="Binance REST High Rate",
                level="WARNING",
                metadata={
                    "pid": os.getpid(),
                    "endpoint": endpoint,
                    "caller": caller,
                    "rolling_60s_requests": rolling,
                    "endpoint_calls_since_start": _binance_counts[endpoint],
                    "interval_since_same_endpoint_ms": interval_ms,
                    "success": success,
                    "elapsed_ms": elapsed_ms,
                },
            )

        _emit_binance_summary(now, rolling)


def _wrap_binance_method(name, original):
    @functools.wraps(original)
    def wrapped(*args, **kwargs):
        start = time.monotonic()
        caller = _binance_caller()
        success = False
        try:
            result = original(*args, **kwargs)
            success = True
            return result
        finally:
            _record_binance_call(
                name,
                success,
                (time.monotonic() - start) * 1000.0,
                caller,
            )
    wrapped._langfuse_binance_monitor = True
    return wrapped


def install_binance_rest_monitor():
    global _binance_patched
    if _binance_patched:
        return
    try:
        from binance.client import Client
    except Exception as exc:
        logger.warning(f"Binance REST monitor unavailable: {exc}")
        return

    patched = 0
    for name in dir(Client):
        if not name.startswith("futures_"):
            continue
        try:
            original = getattr(Client, name)
            if not callable(original) or getattr(original, "_langfuse_binance_monitor", False):
                continue
            setattr(Client, name, _wrap_binance_method(name, original))
            patched += 1
        except Exception:
            continue

    _binance_patched = True
    logger.info(f"Binance REST Langfuse monitor attached: {patched} futures methods")


# Initialize on module import, then attach to the python-binance Client used by bot.py.
init_telemetry()
install_binance_rest_monitor()
