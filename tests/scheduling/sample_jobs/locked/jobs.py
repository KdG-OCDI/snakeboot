import threading
from datetime import timedelta

from snakeboot.scheduling import scheduled, scheduler_lock
from snakeboot.stereotype import component
from snakeboot.tracing import TraceContext


@component
class HourlyReport:
    """A job that one replica at a time may run; it remembers the trace of every run."""

    def __init__(self) -> None:
        self.traces: list[str | None] = []
        self.ran_twice = threading.Event()

    @scheduled(fixed_delay=timedelta(milliseconds=10))
    @scheduler_lock("hourly-report", at_most_for=timedelta(minutes=50), at_least_for=timedelta(minutes=1))
    def send(self) -> None:
        span = TraceContext.current()
        self.traces.append(span.trace_id if span is not None else None)
        if len(self.traces) >= 2:  # two runs show that each has a trace of its own
            self.ran_twice.set()
