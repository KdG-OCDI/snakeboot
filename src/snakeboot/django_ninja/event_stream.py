from collections.abc import Awaitable, Callable
from typing import Final

from asgiref.sync import sync_to_async
from django.db import close_old_connections
from django.http import StreamingHttpResponse

from snakeboot.rest import ServerSentEvents

STREAM_HEADERS: Final = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
"""No cache may keep the stream, and no proxy (nginx's buffering, for one) may hold back its events."""


def event_stream_response(events: ServerSentEvents, status: int) -> StreamingHttpResponse:
    """Returns the Django response that streams `events` as `text/event-stream`.

    The stream is an async iterator, so under ASGI a watching client holds no thread while nothing happens.
    """
    return StreamingHttpResponse(
        events.encoded(django_blocking), content_type="text/event-stream", status=status, headers=STREAM_HEADERS
    )


def django_blocking[T](work: Callable[[], T]) -> Awaitable[T]:
    """Runs synchronous work of a stream as Django runs a synchronous view under ASGI: on the thread of the request's
    synchronous code, between fresh database connections, so a stream that runs for half an hour survives a
    database that went away.
    """

    def with_fresh_connections() -> T:
        close_old_connections()
        try:
            return work()
        finally:
            close_old_connections()

    return sync_to_async(with_fresh_connections)()
