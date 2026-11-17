"""The table of the stream offsets, in snakeboot's own terms: an entity, its repository and the offsets kept in it.

Every application with `[database]` maps it, but its table is part of the schema only once the application has a
stream listener: then `make_migration` writes it into the application's migrations.
"""

from dataclasses import dataclass
from typing import Annotated, Protocol, override

from snakeboot.data import BigInt, Column, CrudRepository, Id, entity
from snakeboot.events.stream_offsets import STREAM_CONSUMER_ATTRIBUTE, StreamOffsets


@entity("snakeboot_stream_offset", needed_by=STREAM_CONSUMER_ATTRIBUTE)
@dataclass
class StreamOffsetRecord:
    """How far one consumer has read its stream: the offset of the last event it handled."""

    consumer: Annotated[str, Id(), Column(length=500)]
    last_offset: Annotated[int, BigInt()]


class StreamOffsetRecords(CrudRepository[StreamOffsetRecord, str], Protocol):
    """The offset of every consumer of a stream."""


class RepositoryStreamOffsets(StreamOffsets):
    """Keeps the offsets in the application's database, in the transaction that handled the event.

    The projection a consumer builds and the offset it read up to commit together, so after a restart the consumer
    neither skips an event nor handles one twice.
    """

    def __init__(self, records: StreamOffsetRecords) -> None:
        self._records = records

    @override
    def last_handled(self, consumer: str) -> int | None:
        record = self._records.find_by_id(consumer)
        return record.last_offset if record is not None else None

    @override
    def handled(self, consumer: str, offset: int) -> None:
        record = self._records.find_by_id(consumer) or StreamOffsetRecord(consumer, offset)
        record.last_offset = offset
        self._records.save(record)
