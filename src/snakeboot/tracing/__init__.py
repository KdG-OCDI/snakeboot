"""Technical library: which trace the work in hand belongs to, like Micrometer Tracing in Spring Boot.

    with TraceContext.started(headers.get("traceparent")):    # continue the caller's trace, or start one
        TraceContext.current().trace_id                        # in every log line of the work

The web binding starts a span for every call, the RabbitMQ listeners for every message, the scheduler for every run;
the `RabbitTemplate` hands the `traceparent` on. Log lines carry the trace id, so a request can be followed through
every service it reaches. It uses the standard library only, and propagates W3C Trace Context; it exports no spans.
"""

from snakeboot.tracing.trace_context import TRACEPARENT, TraceContext

__all__ = ["TRACEPARENT", "TraceContext"]
