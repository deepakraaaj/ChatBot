
import logging
import uuid
import contextvars
import json
import time
from functools import wraps
from typing import Optional, Dict, Any

# Context Variables for Trace Context
_trace_id_ctx = contextvars.ContextVar("trace_id", default=None)
_span_id_ctx = contextvars.ContextVar("span_id", default=None)

class TraceManager:
    """
    Manages structured logging and tracing context.
    Currently uses standard Python logging but formatted as JSON for easy ingestion.
    """
    
    @staticmethod
    def get_trace_id() -> str:
        tid = _trace_id_ctx.get()
        if not tid:
            tid = str(uuid.uuid4())
            _trace_id_ctx.set(tid)
        return tid

    @staticmethod
    def set_trace_id(trace_id: str):
        _trace_id_ctx.set(trace_id)

    @staticmethod
    def log(level: str, message: str, extra: Optional[Dict[str, Any]] = None):
        """
        Structured log emission.
        """
        payload = {
            "timestamp": time.time(),
            "level": level.upper(),
            "message": message,
            "trace_id": TraceManager.get_trace_id(),
            "span_id": _span_id_ctx.get(),
            **(extra or {})
        }
        # In a real system, this would go to a specialized logger/aggregator
        # For now, we print JSON to stdout so it can be captured by vector/fluentd or just read
        print(json.dumps(payload))

    @staticmethod
    def info(message: str, **kwargs):
        TraceManager.log("INFO", message, kwargs)

    @staticmethod
    def error(message: str, exc: Optional[Exception] = None, **kwargs):
        extra = kwargs
        if exc:
            extra["error"] = str(exc)
            extra["error_type"] = type(exc).__name__
        TraceManager.log("ERROR", message, extra)

    @staticmethod
    def span(name: str):
        """
        Decorator to trace a function execution as a span.
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                parent_span = _span_id_ctx.get()
                current_span = str(uuid.uuid4())
                _span_id_ctx.set(current_span)
                
                start_time = time.time()
                TraceManager.info(f"Start Span: {name}", span_name=name, parent_span=parent_span)
                
                try:
                    result = await func(*args, **kwargs)
                    duration = time.time() - start_time
                    TraceManager.info(f"End Span: {name}", span_name=name, duration_ms=duration*1000)
                    return result
                except Exception as e:
                    duration = time.time() - start_time
                    TraceManager.error(f"Error Span: {name}", exc=e, span_name=name, duration_ms=duration*1000)
                    raise
                finally:
                    # Reset context (basic handling, for nested async be careful)
                    _span_id_ctx.set(parent_span)
            return wrapper
        return decorator

# Setup basic configuration if needed
logging.basicConfig(level=logging.INFO)
