import json
import logging
from datetime import UTC, datetime
from typing import Any, Final, override

ECS_VERSION: Final = "8.11"
"""The version of the Elastic Common Schema the lines follow."""


class EcsFormatter(logging.Formatter):
    """Writes a log record as one line of JSON in the Elastic Common Schema, like Spring Boot's `ecs` format.

    The time in UTC, the level, the logger, the process and its thread, the service, the trace and span ids of the
    work in hand (`TraceLogFilter` puts them on the record), the message, and an error with its stack trace.
    """

    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    @override
    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, Any] = {
            "@timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "log": {"level": record.levelname, "logger": record.name},
            "process": {"pid": record.process, "thread": {"name": record.threadName}},
            "service": {"name": self._service},
            "message": record.getMessage(),
            "ecs": {"version": ECS_VERSION},
        }
        if trace_id := getattr(record, "trace_id", None):
            line["trace"] = {"id": trace_id}
            line["span"] = {"id": getattr(record, "span_id", None)}
        if record.exc_info is not None and record.exc_info[1] is not None:
            error = record.exc_info[1]
            line["error"] = {
                "type": type(error).__qualname__,
                "message": str(error),
                "stack_trace": self.formatException(record.exc_info),
            }
        return json.dumps(line, default=str, ensure_ascii=False)
