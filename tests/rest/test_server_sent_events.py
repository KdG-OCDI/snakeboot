"""Server-sent events: what a stream sends, when it sends a heartbeat, and when it ends, in no framework's terms."""

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import timedelta
from itertools import count

import pytest
from pydantic import BaseModel

from snakeboot.rest import ServerSentEvent, ServerSentEvents
from snakeboot.rest.server_sent_events import KEEP_ALIVE

INSTANTLY = timedelta(0)
BRIEFLY = timedelta(milliseconds=20)


@dataclass(frozen=True)
class GameDTO:
    version: int
    status: str


class ScoreModel(BaseModel):
    points: int


def collect(events: ServerSentEvents, limit: int = 100) -> list[str]:
    """What a client receives, at most `limit` parts."""

    async def receive() -> list[str]:
        received: list[str] = []
        stream = events.encoded()
        async for part in stream:
            received.append(part)
            if len(received) == limit:
                await stream.aclose()  # type: ignore[attr-defined]
        return received

    return asyncio.run(receive())


async def events_of(*events: ServerSentEvent) -> AsyncIterator[ServerSentEvent]:
    for event in events:
        yield event


def test_an_event_is_its_fields_one_per_line_then_an_empty_line() -> None:
    assert ServerSentEvent("hello", event="greeting", id="7").encoded() == "event: greeting\nid: 7\ndata: hello\n\n"


def test_an_event_without_name_or_id_is_its_data_only() -> None:
    assert ServerSentEvent("hello").encoded() == "data: hello\n\n"


def test_data_of_several_lines_is_one_data_field_per_line() -> None:
    assert ServerSentEvent("one\ntwo\r\nthree").encoded() == "data: one\ndata: two\ndata: three\n\n"


@pytest.mark.parametrize(
    ("data", "json"),
    [
        (GameDTO(version=3, status="won"), '{"version":3,"status":"won"}'),
        (ScoreModel(points=12), '{"points":12}'),
        ({"cells": [1, 2]}, '{"cells":[1,2]}'),
    ],
    ids=["dataclass", "pydantic model", "dict"],
)
def test_data_that_is_no_text_is_json(data: object, json: str) -> None:
    assert ServerSentEvent(data).encoded() == f"data: {json}\n\n"


@pytest.mark.parametrize("field", ["event", "id"])
def test_a_name_or_id_of_two_lines_is_refused(field: str) -> None:
    with pytest.raises(ValueError, match=f"The {field} of a server-sent event is one line"):
        ServerSentEvent("data", **{field: "two\nlines"})


def test_a_stream_sends_what_its_source_yields_then_ends() -> None:
    events = ServerSentEvents(events_of(ServerSentEvent("a"), ServerSentEvent("b")))

    assert collect(events) == ["data: a\n\n", "data: b\n\n"]


def test_a_silent_stream_sends_a_comment_to_keep_the_connection_open() -> None:
    async def slow() -> AsyncIterator[ServerSentEvent]:
        await asyncio.sleep(0.1)
        yield ServerSentEvent("late")

    received = collect(ServerSentEvents(slow(), heartbeat=BRIEFLY))

    assert received[0] == KEEP_ALIVE
    assert received[-1] == "data: late\n\n"


def test_a_stream_ends_after_its_timeout_and_closes_its_source() -> None:
    closed: list[bool] = []

    async def endless() -> AsyncIterator[ServerSentEvent]:
        try:
            while True:
                await asyncio.sleep(1)
                yield ServerSentEvent("never")
        finally:
            closed.append(True)

    received = collect(ServerSentEvents(endless(), heartbeat=timedelta(seconds=1), timeout=BRIEFLY))

    assert received == []
    assert closed == [True]


def test_a_client_that_leaves_closes_the_source() -> None:
    closed: list[bool] = []

    async def endless() -> AsyncIterator[ServerSentEvent]:
        try:
            for number in count():
                yield ServerSentEvent(str(number))
        finally:
            closed.append(True)

    assert collect(ServerSentEvents(endless()), limit=2) == ["data: 0\n\n", "data: 1\n\n"]
    assert closed == [True]


def reader(*values: GameDTO) -> Callable[[], GameDTO]:
    """Returns the values one by one, then the last one forever, like a use case that reads a game."""
    remaining = list(values)

    def read() -> GameDTO:
        return remaining.pop(0) if len(remaining) > 1 else remaining[0]

    return read


def finished(game: GameDTO) -> bool:
    return game.status == "won"


def test_watching_reads_right_away_so_an_error_answers_the_call() -> None:
    def unknown_game() -> GameDTO:
        raise LookupError("no such game")

    with pytest.raises(LookupError):
        ServerSentEvents.watching(unknown_game, every=INSTANTLY)


def test_watching_sends_the_value_now_and_every_time_it_changes_until_it_is_final() -> None:
    read = reader(GameDTO(1, "playing"), GameDTO(1, "playing"), GameDTO(2, "playing"), GameDTO(3, "won"))

    events = ServerSentEvents.watching(
        read,
        every=INSTANTLY,
        until=finished,
        as_event=lambda game: ServerSentEvent(game.status, event="game", id=str(game.version)),
    )

    assert collect(events) == [
        "event: game\nid: 1\ndata: playing\n\n",
        "event: game\nid: 2\ndata: playing\n\n",
        "event: game\nid: 3\ndata: won\n\n",
    ]


def test_watching_a_final_value_sends_it_once() -> None:
    events = ServerSentEvents.watching(reader(GameDTO(7, "won")), every=INSTANTLY, until=finished)

    assert collect(events) == ['data: {"version":7,"status":"won"}\n\n']


def test_watching_reads_through_the_runner_the_binding_gives() -> None:
    runs: list[str] = []

    async def recording_runner[T](work: Callable[[], T]) -> T:
        runs.append("blocking")
        return work()

    async def receive() -> list[str]:
        events = ServerSentEvents.watching(
            reader(GameDTO(1, "playing"), GameDTO(2, "won")), every=INSTANTLY, until=finished
        )
        return [part async for part in events.encoded(recording_runner)]

    assert len(asyncio.run(receive())) == 2
    assert runs == ["blocking"]
