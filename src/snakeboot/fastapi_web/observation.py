import time
from typing import Any, Final

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from snakeboot.actuator import MeterRegistry
from snakeboot.tracing import TRACEPARENT, TraceContext

REQUESTS_METRIC: Final = "http_server_requests_seconds"
"""The timer of every call, like Micrometer's `http.server.requests`: tagged with method, uri and status."""


class TracingMiddleware:
    """Runs every call in a span of its own: of the caller's trace when it sends a `traceparent`, of a new one else.

    The span lives in a context variable, which the threads of the synchronous endpoints inherit, so every log line
    of the call carries its trace id and every message it sends carries its `traceparent`.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Calls the application inside a span; other scopes than HTTP pass through."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        with TraceContext.started(_header(scope, TRACEPARENT)):
            await self._app(scope, receive, send)


class RequestMetricsMiddleware:
    """Times every call in the `MeterRegistry`, like Spring Boot's `http.server.requests`.

    The `uri` tag is the route template (`/api/games/{game_id}`), not the path, so the number of series stays small;
    a path no route matches is `NOT_FOUND`, or `UNKNOWN` when it answered otherwise. A call that raises counts as 500.
    """

    def __init__(self, app: ASGIApp, meters: MeterRegistry) -> None:
        self._app = app
        self._meters = meters

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Calls the application and records how long it took to answer."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        started, answered = time.perf_counter(), {"status": 500}

        async def sending(message: Message) -> None:
            if message["type"] == "http.response.start":
                answered["status"] = message["status"]
            await send(message)

        try:
            await self._app(scope, receive, sending)
        finally:
            tags = {
                "method": scope["method"],
                "uri": _uri_of(scope, answered["status"]),
                "status": str(answered["status"]),
            }
            timer = self._meters.timer(REQUESTS_METRIC, "How long the server took to answer a call", tags=tags)
            timer.record(time.perf_counter() - started)


def _uri_of(scope: Scope, status: int) -> str:
    route: Any = scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str):
        return path
    return "NOT_FOUND" if status == 404 else "UNKNOWN"  # noqa: PLR2004  # reason: HTTP's Not Found, as Micrometer tags it


def _header(scope: Scope, name: str) -> str | None:
    wanted = name.encode("latin-1")
    for key, value in scope.get("headers", ()):
        if key.lower() == wanted:
            return bytes(value).decode("latin-1")
    return None
