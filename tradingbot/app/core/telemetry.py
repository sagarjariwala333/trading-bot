import os
import sys
import logging
import functools
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

    # Populate os.environ so Langfuse v4 SDK and OpenTelemetry exporters pick them up globally
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

            # Record log as discrete Langfuse event in v4 SDK
            client.create_event(
                name=f"Log {level}: {record.name}",
                input={"message": msg},
                level="ERROR" if level in ("ERROR", "CRITICAL") else ("WARNING" if level == "WARNING" else "DEFAULT"),
                metadata=metadata
            )
        except Exception:
            # Silence logging telemetry failures so trading bot never crashes
            pass


def observe_trace(name: Optional[str] = None, as_type: Optional[str] = None):
    """
    Decorator to wrap functions as a Langfuse trace/span with safe exception handling.
    """
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
                # Traced function raised an exception
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
    """
    Record an explicit domain event in Langfuse (e.g. Signal Generated, Order Placed, Position Closed).
    """
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


# Initialize on module import
init_telemetry()
