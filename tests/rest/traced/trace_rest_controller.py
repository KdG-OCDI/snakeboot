from snakeboot.rest import rest_controller, route
from snakeboot.tracing import TraceContext


@rest_controller("/trace")
class TraceRestController:
    """Sample controller that answers the trace its call runs in."""

    @route.get("")
    def current_trace(self) -> dict[str, str | None]:
        span = TraceContext.current()
        return {"trace_id": span.trace_id if span is not None else None}
