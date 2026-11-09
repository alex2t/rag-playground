"""JSON log lines on standard output (D37), with Python's built-in logging."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

# Set by the request middleware; background jobs' threads do not inherit it, so their lines carry no request id.
request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    """Format a record as one JSON object: time (UTC), level, logger, message, the current request's id if any, plus
    the record's `fields`."""

    def format(self, record: logging.LogRecord) -> str:
        line = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if (current := request_id.get()) is not None:
            line["request_id"] = current
        line.update(getattr(record, "fields", {}))
        return json.dumps(line)


def setup() -> None:
    """Send the app's loggers (`rag_playground.*`) to standard output as JSON lines, from INFO up."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("rag_playground")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
