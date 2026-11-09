import logging
import logging.config
from typing import override

from snakeboot.application.ecs_formatter import EcsFormatter
from snakeboot.configuration import LoggingProperties, ServerProperties
from snakeboot.tracing import TraceContext

PLAIN_FORMAT = "%(asctime)s %(levelname)s%(trace)s %(name)s: %(message)s"
"""A plain line: the time, the level, the trace id of the work in hand (when there is one), the logger, the message."""


class TraceLogFilter(logging.Filter):
    """Puts the trace and span ids of the work in hand on every record, like the MDC of Spring Boot's tracing.

    `trace_id` and `span_id` are empty outside a span; `trace` is ` [<trace id>]` for a plain line, or nothing.
    """

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        span = TraceContext.current()
        record.trace_id = span.trace_id if span is not None else ""
        record.span_id = span.span_id if span is not None else ""
        record.trace = f" [{span.trace_id}]" if span is not None else ""
        return True


def configure_logging(server: ServerProperties, logging_properties: LoggingProperties | None, *, service: str) -> None:
    """Logs to the console from `[server] log_level` up, like Spring Boot's `logging.level.root`.

    A line is plain text, or one JSON object in the Elastic Common Schema with `[logging] format = "ecs"`; both carry
    the trace id of the work in hand. pika reports every step of every connection at INFO, and Alembic every plugin it
    loads; like Spring Boot's clients, only their problems show.
    """
    structured = logging_properties is not None and logging_properties.format == "ecs"
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"trace": {"()": TraceLogFilter}},
            "formatters": {
                "plain": {"format": PLAIN_FORMAT},
                "ecs": {"()": EcsFormatter, "service": service},
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "ecs" if structured else "plain",
                    "filters": ["trace"],
                }
            },
            "root": {"handlers": ["console"], "level": server.log_level},
            "loggers": {"pika": {"level": "WARNING"}, "alembic": {"level": "WARNING"}},
        }
    )
