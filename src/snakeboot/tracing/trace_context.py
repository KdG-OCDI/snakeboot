import re
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Final, Self

TRACEPARENT: Final = "traceparent"
"""The header that carries a trace from one service to the next, in HTTP and in messages (W3C Trace Context)."""

_TRACEPARENT: Final = re.compile(r"00-(?P<trace_id>[0-9a-f]{32})-(?P<span_id>[0-9a-f]{16})-[0-9a-f]{2}")
_INVALID_TRACE_ID: Final = "0" * 32


@dataclass(frozen=True, slots=True)
class TraceContext:
    """Which trace the work in hand belongs to, like Micrometer Tracing's `TraceContext` in Spring Boot.

    A call, a message or a scheduled run starts a span: it continues the trace of the `traceparent` it came with, or
    starts a trace of its own. Every log line of the work carries the trace id, and every message it sends carries the
    `traceparent`, so one request can be followed through every service it reaches, in the logs of each.

        with TraceContext.started(headers.get("traceparent")):
            handle(message)

    The context lives in a context variable, so each thread, and each task of an event loop, has its own.
    """

    trace_id: str
    span_id: str

    @classmethod
    def current(cls) -> Self | None:
        """Returns the span of the work in hand, or None outside one."""
        current = _CURRENT.get()
        return current if isinstance(current, cls) else None

    @classmethod
    @contextmanager
    def started(cls, traceparent: str | None = None) -> Iterator["TraceContext"]:
        """Runs the block in a new span: of the trace `traceparent` names, or of a new trace without a valid one."""
        span = TraceContext(_trace_id_of(traceparent) or secrets.token_hex(16), secrets.token_hex(8))
        token = _CURRENT.set(span)
        try:
            yield span
        finally:
            _CURRENT.reset(token)

    @property
    def traceparent(self) -> str:
        """The `traceparent` header that hands this span to the next service: version 00, sampled."""
        return f"00-{self.trace_id}-{self.span_id}-01"


_CURRENT: Final[ContextVar[TraceContext | None]] = ContextVar("snakeboot-trace", default=None)


def _trace_id_of(traceparent: str | None) -> str | None:
    named = _TRACEPARENT.fullmatch(traceparent.strip().lower()) if traceparent else None
    if named is None or named["trace_id"] == _INVALID_TRACE_ID:
        return None
    return named["trace_id"]
