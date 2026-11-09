"""JSON log lines on standard output (D37), with Python's built-in logging."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

from rag_playground.settings import settings

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
        if record.exc_info:
            line["exception"] = self.formatException(record.exc_info)
        return json.dumps(line)


class ErrorFile(logging.Handler):
    """Append each error line to `<var_dir>/errors.log`, which outlives the container (D37). The folder is read
    when the line is written, so it follows `settings.var_dir`."""

    def emit(self, record: logging.LogRecord) -> None:
        settings.var_dir.mkdir(parents=True, exist_ok=True)
        with open(settings.var_dir / "errors.log", "a", encoding="utf-8") as file:
            file.write(self.format(record) + "\n")


def setup() -> None:
    """Send the app's loggers (`rag_playground.*`) to standard output as JSON lines, from INFO up, and errors also
    to `errors.log`."""
    out = logging.StreamHandler(sys.stdout)
    out.setFormatter(JsonFormatter())
    errors = ErrorFile(logging.ERROR)
    errors.setFormatter(JsonFormatter())
    logger = logging.getLogger("rag_playground")
    logger.addHandler(out)
    logger.addHandler(errors)
    logger.setLevel(logging.INFO)
