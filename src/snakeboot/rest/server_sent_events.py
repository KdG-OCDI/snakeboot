import asyncio
import re
from collections.abc import AsyncGenerator, AsyncIterable, AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Final, Protocol

import pydantic_core

HEARTBEAT: Final = timedelta(seconds=15)
"""How long a stream stays silent before a comment keeps proxies and browsers from closing it."""

TIMEOUT: Final = timedelta(minutes=30)
"""How long a stream lasts at most, like the timeout of Spring's `SseEmitter`; the browser's EventSource reconnects."""

KEEP_ALIVE: Final = ": keep-alive\n\n"
"""The comment a silent stream sends: clients ignore it, proxies see traffic."""

_LINE_BREAK: Final = re.compile(r"\r\n|\r|\n")
"""What ends a line in `text/event-stream`, and nothing else."""


class BlockingRunner(Protocol):
    """Runs synchronous work, such as a use case, from a stream without holding up the server.

    The binding of the web framework supplies it, with whatever the framework needs around such work (fresh
    database connections, for one); `asyncio.to_thread` is one without anything around it.
    """

    def __call__[T](self, work: Callable[[], T], /) -> Awaitable[T]:
        """Returns an awaitable of what `work` returns."""


@dataclass(frozen=True, slots=True)
class ServerSentEvent:
    """One event of a stream, like Spring's `ServerSentEvent`: its data, and optionally its name and id.

    `data` that is a string is sent as it is; anything else (a dataclass, a Pydantic model, a dict) as JSON, the
    JSON a REST answer would hold. `event` names the event for the browser's `addEventListener`; `id` comes back
    as `Last-Event-ID` when the browser reconnects.
    """

    data: Any
    event: str | None = None
    id: str | None = None

    def __post_init__(self) -> None:
        """Refuses a name or id that would break the stream: a line break ends a field."""
        for field, value in (("event", self.event), ("id", self.id)):
            if value is not None and ("\n" in value or "\r" in value):
                raise ValueError(f"The {field} of a server-sent event is one line, got {value!r}.")

    def encoded(self) -> str:
        """Returns the event as `text/event-stream` writes it: one field per line, an empty line after."""
        lines = [f"{field}: {value}" for field, value in (("event", self.event), ("id", self.id)) if value is not None]
        lines.extend(f"data: {line}" for line in _LINE_BREAK.split(_text_of(self.data)))
        return "\n".join(lines) + "\n\n"


type EventSource = Callable[[BlockingRunner], AsyncIterable[ServerSentEvent]]


class ServerSentEvents:
    """What an endpoint returns to stream events, like Spring's `SseEmitter` or a `Flux<ServerSentEvent>`.

    The stream sends what its source yields, a comment when nothing was sent for `heartbeat`, and ends when the
    source ends or `timeout` has passed; the binding of the web framework serves it as `text/event-stream`, so the
    controller stays a plain method. The source is an async iterable of events, or a function that receives a
    `BlockingRunner` and returns one, for a source that reads with synchronous use cases. Most endpoints watch a
    value instead:

        @route.get("/games/{game_id}/events")
        def watch_game(self, game_id: str) -> ServerSentEvents:
            return ServerSentEvents.watching(
                lambda: self._get_game.execute(GetGameRequestDTO(game_id=game_id)),
                every=timedelta(milliseconds=500),
                until=lambda game: game.status in FINAL_STATUSES,
                as_event=lambda game: ServerSentEvent(game, event="game", id=str(game.version)),
            )
    """

    def __init__(
        self,
        events: AsyncIterable[ServerSentEvent] | EventSource,
        *,
        heartbeat: timedelta = HEARTBEAT,
        timeout: timedelta = TIMEOUT,
    ) -> None:
        self._source: EventSource = events if callable(events) else _always(events)
        self.heartbeat = heartbeat
        self.timeout = timeout

    @classmethod
    def watching[T](
        cls,
        read: Callable[[], T],
        *,
        every: timedelta,
        until: Callable[[T], bool] = lambda _value: False,
        as_event: Callable[[T], ServerSentEvent] = ServerSentEvent,
    ) -> "ServerSentEvents":
        """Streams what `read` returns: now, then every time it changes, until `until` holds for it.

        `read` runs once right away, in the call of the endpoint, so an error (an unknown id) answers the call
        as any error does; after that every `every`, through the binding's `BlockingRunner`. A value is sent when
        it differs (`!=`) from the last one sent, as `as_event` makes it an event.
        """
        first = read()

        async def watch(blocking: BlockingRunner) -> AsyncIterator[ServerSentEvent]:
            sent = first
            yield as_event(sent)
            while not until(sent):
                await asyncio.sleep(every.total_seconds())
                if (latest := await blocking(read)) != sent:
                    sent = latest
                    yield as_event(sent)

        return cls(watch)

    async def encoded(self, blocking: BlockingRunner = asyncio.to_thread) -> AsyncIterator[str]:
        """Yields the stream as `text/event-stream`: the events, with a comment in every silence of `heartbeat`."""
        async for event in _with_silences(self._source(blocking), self.heartbeat, self.timeout):
            yield KEEP_ALIVE if event is None else event.encoded()


def _always(events: AsyncIterable[ServerSentEvent]) -> EventSource:
    def source(_blocking: BlockingRunner) -> AsyncIterable[ServerSentEvent]:
        return events

    return source


def _text_of(data: Any) -> str:
    return data if isinstance(data, str) else pydantic_core.to_json(data).decode()


class _End:
    """What a source gives once it has nothing more to give."""


async def _next_of(events: AsyncIterator[ServerSentEvent]) -> ServerSentEvent | _End:
    try:
        return await anext(events)
    except StopAsyncIteration:
        return _End()


async def _with_silences(
    source: AsyncIterable[ServerSentEvent], heartbeat: timedelta, timeout: timedelta
) -> AsyncIterator[ServerSentEvent | None]:
    # Waits for the next event without cancelling it when a heartbeat is due, so a slow source loses nothing;
    # None marks a silence. Whatever ends the stream (the source, the timeout, a client that left), the source
    # is stopped and closed.
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout.total_seconds()
    events = aiter(source)
    pending: asyncio.Task[ServerSentEvent | _End] | None = None
    try:
        while (remaining := deadline - loop.time()) > 0:
            pending = pending or asyncio.ensure_future(_next_of(events))
            done, _ = await asyncio.wait({pending}, timeout=min(remaining, heartbeat.total_seconds()))
            if done:
                event, pending = pending.result(), None
                if isinstance(event, _End):
                    return
                yield event
            elif loop.time() < deadline:  # a stream that ends sends no heartbeat first
                yield None
    finally:
        await _stop(pending, events)


async def _stop(pending: asyncio.Task[ServerSentEvent | _End] | None, events: AsyncIterator[ServerSentEvent]) -> None:
    if pending is not None and not pending.done():
        pending.cancel()
        await asyncio.wait({pending})
    if isinstance(events, AsyncGenerator):
        await events.aclose()
