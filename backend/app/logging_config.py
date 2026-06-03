"""Application logging configuration and request correlation helpers."""
import logging
import sys
from contextvars import ContextVar

from app.config import settings

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Attach the current request id to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_context.get()
        return True


def configure_logging() -> None:
    """Configure console logging with stable fields for local and container use."""
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    formatter = logging.Formatter(settings.LOG_FORMAT)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)

    logging.getLogger("uvicorn.access").setLevel(level)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def set_request_id(request_id: str):
    """Set request id for the current context and return a reset token."""
    return request_id_context.set(request_id)


def reset_request_id(token) -> None:
    """Reset request id context after request handling."""
    request_id_context.reset(token)


def get_request_id() -> str:
    """Return current request id for explicit log messages or responses."""
    return request_id_context.get()
