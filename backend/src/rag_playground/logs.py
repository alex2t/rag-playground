"""JSON log lines on standard output (D37), with Python's built-in logging."""

import json
import logging
import sys
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    """Format a record as one JSON object: time (UTC), level, logger, message, plus the record's `fields`."""

    def format(self, record: logging.LogRecord) -> str:
        line = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        line.update(getattr(record, "fields", {}))
        return json.dumps(line)


def setup() -> None:
    """Send the app's loggers (`rag_playground.*`) to standard output as JSON lines, from INFO up."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("rag_playground")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
