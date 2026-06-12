import json
import logging
import sys


class _JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "service": "agent",
            "event": record.getMessage(),
        })


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    logging.basicConfig(handlers=[handler], level=logging.INFO, force=True)
