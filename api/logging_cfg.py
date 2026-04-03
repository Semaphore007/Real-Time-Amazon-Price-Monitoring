"""
Structured JSON logging configuration.

Sets up:
  - Console handler (coloured in dev, plain in prod)
  - JSON formatter for production log shipping
  - Request-ID context var propagated through FastAPI middleware
"""
from __future__ import annotations

import json
import logging
import sys
import time
from contextvars import ContextVar
from typing import Callable
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Per-request correlation ID (set by RequestLoggingMiddleware)
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class _JsonFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log: dict = {
            "ts":      self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level":   record.levelname,
            "logger":  record.name,
            "msg":     record.getMessage(),
            "request_id": request_id_var.get("-"),
        }
        if record.exc_info:
            log["exc"] = self.formatException(record.exc_info)
        return json.dumps(log, ensure_ascii=False)


class _DevFormatter(logging.Formatter):
    """Human-readable coloured formatter for development."""
    _COLOURS = {
        "DEBUG":    "\033[36m",
        "INFO":     "\033[32m",
        "WARNING":  "\033[33m",
        "ERROR":    "\033[31m",
        "CRITICAL": "\033[35m",
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        colour = self._COLOURS.get(record.levelname, "")
        rid    = request_id_var.get("-")
        prefix = f"{colour}{record.levelname:<8}{self._RESET}"
        return (
            f"{self.formatTime(record, '%H:%M:%S')} {prefix} "
            f"[{rid[:8]}] {record.name}: {record.getMessage()}"
        )


def setup_logging(environment: str = "development", level: str = "INFO") -> None:
    """Call once at app startup to configure root logger."""
    root = logging.getLogger()
    root.setLevel(level)

    # Remove any existing handlers (e.g. uvicorn adds its own)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if environment == "production":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(_DevFormatter())

    root.addHandler(handler)

    # Quieten noisy third-party loggers
    for name in ("uvicorn.access", "scrapy", "playwright", "asyncio"):
        logging.getLogger(name).setLevel(logging.WARNING)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Assigns a unique request-ID to every HTTP request and logs
    method, path, status, and latency.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        rid   = request.headers.get("X-Request-ID", str(uuid4()))
        token = request_id_var.set(rid)
        start = time.perf_counter()

        logger = logging.getLogger("api.access")
        logger.info("%s %s — start", request.method, request.url.path)

        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled exception in %s %s", request.method, request.url.path)
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            status     = getattr(response, "status_code", 0)
            logger.info(
                "%s %s → %d  %.1f ms",
                request.method, request.url.path, status, elapsed_ms,
            )
            request_id_var.reset(token)

        response.headers["X-Request-ID"] = rid
        return response
