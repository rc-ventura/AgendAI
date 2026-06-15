import json
import logging
import sys
from contextvars import ContextVar

_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(value: str) -> None:
    """Set the request_id for the current execution context (read by _JsonFormatter)."""
    _request_id_var.set(value)


class _JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "service": "agent",
            "request_id": _request_id_var.get(),
            "event": record.getMessage(),
        })


def configure_logging() -> None:
    root = logging.getLogger()
    # Always enforce the level first. The LangGraph Server (uvicorn) installs its
    # own root handlers before importing the graph, so if we guard on handlers
    # before setLevel, the agent's INFO logs would silently disappear whenever the
    # server's default level is above INFO.
    root.setLevel(logging.INFO)
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root.addHandler(handler)
