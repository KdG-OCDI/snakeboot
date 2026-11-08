from typing import Final

from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse

from snakeboot.rest import ServerSentEvents

STREAM_HEADERS: Final = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
"""No cache may keep the stream, and no proxy (nginx's buffering, for one) may hold back its events."""


class EventStreamResponse(StreamingResponse):
    """A streamed `text/event-stream` answer; the OpenAPI document names that media type for the endpoint."""

    media_type = "text/event-stream"


def event_stream_response(events: ServerSentEvents, status: int) -> EventStreamResponse:
    """Returns the response that streams `events`, uncached and unbuffered.

    The stream is an async iterator, so a watching client holds no thread while nothing happens; its synchronous
    reads run on the server's thread pool, as a synchronous endpoint does.
    """
    return EventStreamResponse(events.encoded(run_in_threadpool), status_code=status, headers=STREAM_HEADERS)
