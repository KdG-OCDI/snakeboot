"""The table of the stream offsets, in snakeboot's own terms: an entity, its repository and the offsets kept in it.

Every application with `[database]` maps it, but its table is part of the schema only once the application has a
stream listener: then `make_migration` writes it into the application's migrations.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Annotated, Protocol, override

from snakeboot.data import BigInt, Column, CrudRepository, Id, entity, query
from snakeboot.events.stream_offsets import STREAM_CONSUMER_ATTRIBUTE, StreamEvent, StreamOffsets, StreamPosition


@entity("snakeboot_stream_offset", needed_by=STREAM_CONSUMER_ATTRIBUTE)
@dataclass
class StreamOffsetRecord:
    """How far one consumer has read its stream: the offset and the fingerprint of the last event it handled, none
    when it handled none since it started over, and how often it started over."""

    consumer: Annotated[str, Id(), Column(length=500)]
    last_offset: Annotated[int | None, BigInt()] = None
    fingerprint: Annotated[str | None, Column(length=64)] = None
    generation: int = 0


class StreamOffsetRecords(CrudRepository[StreamOffsetRecord, str], Protocol):
    """The offset of every consumer of a stream, each moved forward with one statement."""

    @query(
        "INSERT INTO snakeboot_stream_offset (consumer, last_offset, fingerprint, generation) "
        "VALUES (:consumer, :offset, :fingerprint, :generation) "
        "ON CONFLICT (consumer) DO UPDATE SET last_offset = :offset, fingerprint = :fingerprint "
        "WHERE snakeboot_stream_offset.generation = :generation AND "
        "(snakeboot_stream_offset.last_offset IS NULL OR snakeboot_stream_offset.last_offset < :offset)",
        modifying=True,
    )
    def move_forward(self, consumer: str, *, offset: int, fingerprint: str, generation: int) -> int:
        """Sets the offset of `consumer` to `offset` when it is behind it in `generation`, and locks its row until
        the transaction ends; returns 1 when it moved, 0 when the consumer was there already or started over."""
        ...

    @query(
        "UPDATE snakeboot_stream_offset SET last_offset = NULL, fingerprint = NULL, generation = generation + 1 "
        "WHERE consumer = :consumer AND generation = :generation AND last_offset = :offset",
        modifying=True,
    )
    def start_over(self, consumer: str, *, offset: int, generation: int) -> int:
        """Empties the offset of `consumer` and starts its next generation, when it is still at `offset` in
        `generation`; returns 1 when it did, 0 when another process moved it or started over already."""
        ...


class RepositoryStreamOffsets(StreamOffsets):
    """Keeps the offsets in the application's database, in the transaction that handles the event.

    The projection a consumer builds and the offset it read up to commit together, so after a restart the consumer
    neither skips an event nor handles one twice. The claim is one statement that locks the consumer's row: when
    several processes of a service read the same stream, the second waits for the first one's transaction and then
    finds the event handled. Starting over is one statement too, so of those processes one does it.
    """

    def __init__(self, records: StreamOffsetRecords) -> None:
        self._records = records

    @override
    def position(self, consumer: str) -> StreamPosition:
        record = self._records.find_by_id(consumer)
        if record is None:
            return StreamPosition()
        if record.last_offset is None:
            return StreamPosition(record.generation)
        return StreamPosition(record.generation, StreamEvent(record.last_offset, record.fingerprint or ""))

    @override
    @contextmanager
    def claiming(self, consumer: str, event: StreamEvent, *, generation: int = 0) -> Iterator[bool]:
        moved = self._records.move_forward(
            consumer, offset=event.offset, fingerprint=event.fingerprint, generation=generation
        )
        yield moved == 1  # the transaction's rollback undoes it

    @override
    def start_over(self, consumer: str, seen: StreamPosition) -> bool:
        if seen.last is None:
            return False
        return self._records.start_over(consumer, offset=seen.last.offset, generation=seen.generation) == 1
