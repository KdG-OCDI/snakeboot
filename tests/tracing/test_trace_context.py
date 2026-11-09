"""A span continues the trace of the `traceparent` it came with, or starts a trace of its own."""

from snakeboot.tracing import TraceContext

CALLER = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def test_outside_a_span_there_is_no_trace() -> None:
    assert TraceContext.current() is None


def test_a_span_continues_the_trace_of_its_traceparent_with_a_span_of_its_own() -> None:
    with TraceContext.started(CALLER) as span:
        assert TraceContext.current() is span
        assert span.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
        assert span.span_id != "00f067aa0ba902b7"
        assert span.traceparent == f"00-4bf92f3577b34da6a3ce929d0e0e4736-{span.span_id}-01"
    assert TraceContext.current() is None


def test_without_a_traceparent_a_span_starts_a_trace() -> None:
    with TraceContext.started() as first, TraceContext.started() as second:
        assert len(first.trace_id) == 32
        assert len(first.span_id) == 16
        assert first.trace_id != second.trace_id


def test_a_traceparent_that_is_not_one_starts_a_trace() -> None:
    for broken in ("", "garbage", "00-" + "0" * 32 + "-00f067aa0ba902b7-01", CALLER.replace("-01", "")):
        with TraceContext.started(broken) as span:
            assert span.trace_id != "4bf92f3577b34da6a3ce929d0e0e4736"
            assert span.trace_id != "0" * 32


def test_the_span_inside_ends_where_the_outer_one_resumes() -> None:
    with TraceContext.started(CALLER) as outer:
        with TraceContext.started():
            pass
        assert TraceContext.current() is outer
