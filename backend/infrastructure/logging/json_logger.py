"""
Structured JSON logging infrastructure.
"""
import os
import json
import logging
from logging.handlers import RotatingFileHandler
from contextvars import ContextVar

# Create logs directory if not exists
os.makedirs("logs", exist_ok=True)

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class JSONFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get(),
        }
        for field in ("tenant_id", "user_id", "route", "status_code", "execution_time_ms"):
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        return json.dumps(payload)


logger = logging.getLogger("holomenu")
logger.setLevel(logging.INFO)

# Stream handler for stdout/terminal
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(JSONFormatter())
logger.addHandler(stream_handler)

# Rotating File Handler for logs/holomenu.jsonl (Section 2.4)
file_handler = RotatingFileHandler(
    "logs/holomenu.jsonl", maxBytes=10_000_000, backupCount=5
)
file_handler.setFormatter(JSONFormatter())
logger.addHandler(file_handler)
