"""The table of the stream offsets, in snakeboot's own terms: an entity, its repository and the offsets kept in it.

Every application with `[database]` maps it, but its table is part of the schema only once the application has a
stream listener: then `make_migration` writes it into the application's migrations.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Annotated, Protocol, override

from snakeboot.data import BigInt, Column, CrudRepository, Id, entity, query
from snakeboot.events.stream_offsets import STREAM_CONSUMER_ATTRIBUTE, StreamOffsets


@entity("snakeboot_stream_offset", needed_by=STREAM_CONSUMER_ATTRIBUTE)
@dataclass
class StreamOffsetRecord:
    """How far one consumer has read its stream: the offset of the last event it handled."""

    consumer: Annotated[str, Id(), Column(length=500)]
    last_offset: Annotated[int, BigInt()]


class StreamOffsetRecords(CrudRepository[StreamOffsetRecord, str], Protocol):
    """The offset of every consumer of a stream, each moved forward with one statement."""

    @query(
        "INSERT INTO snakeboot_stream_offset (consumer, last_offset) VALUES (:consumer, :offset) "
        "ON CONFLICT (consumer) DO UPDATE SET last_offset = :offset "
        "WHERE snakeboot_stream_offset.last_offset < :offset",
        modifying=True,
    )
    def move_forward(self, consumer: str, offset: int) -> int:
        """Sets the offset of `consumer` to `offset` when it is behind it, and locks its row until the transaction
        ends; returns 1 when it moved, 0 when the consumer was there already."""
        ...


class RepositoryStreamOffsets(StreamOffsets):
    """Keeps the offsets in the application's database, in the transaction that handles the event.

    The projection a consumer builds and the offset it read up to commit together, so after a restart the consumer
    neither skips an event nor handles one twice. The claim is one statement that locks the consumer's row: when
    several processes of a service read the same stream, the second waits for the first one's transaction and then
    finds the event handled.
    """

    def __init__(self, records: StreamOffsetRecords) -> None:
        self._records = records

    @override
    def last_handled(self, consumer: str) -> int | None:
        record = self._records.find_by_id(consumer)
        return record.last_offset if record is not None else None

    @override
    @contextmanager
    def claiming(self, consumer: str, offset: int) -> Iterator[bool]:
        yield self._records.move_forward(consumer, offset) == 1  # the transaction's rollback undoes it
