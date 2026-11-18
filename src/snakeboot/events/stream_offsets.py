import hashlib
import threading
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from typing import Final, Self, override

STREAM_CONSUMER_ATTRIBUTE: Final = "__snakeboot_stream_consumer__"
"""The mark a stream listener leaves on its method: the table of the stream offsets is needed by it."""


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """One event of a stream: where it is, and what it is.

    The offset alone does not say which stream it is an offset of: a stream that is deleted and declared anew counts
    from 0 again. The fingerprint tells the event from another one at the same offset of a new stream.
    """

    offset: int
    fingerprint: str = ""

    @classmethod
    def of(cls, offset: int, body: bytes, identifier: str | None = None) -> Self:
        """Returns the event at `offset` with the fingerprint of its body and of the identifier its sender gave it."""
        digest = hashlib.sha256((identifier or "").encode())
        digest.update(b"\0")
        digest.update(body)
        return cls(offset, digest.hexdigest())


@dataclass(frozen=True, slots=True)
class StreamPosition:
    """How far a consumer has read its stream: the last event it handled, or None when it handled none yet.

    The generation counts how often the consumer started over, because its stream turned out to be a new one. A claim
    names the generation it read in, so a process that still handles an event of the old stream cannot move the
    position of the new one.
    """

    generation: int = 0
    last: StreamEvent | None = None


class StreamOffsets(ABC):
    """How far each consumer of a stream of events has read, like the offsets Kafka commits for a consumer group.

    A stream keeps every event, so a consumer chooses where it reads from: from the start, to build its projection of
    the events from their history, and afterwards from the event after the last one it handled. The consumer claims
    the offset of an event for the work that handles it, so after a restart it neither skips an event nor handles
    one twice, and of the processes of one service that all read the stream, one handles each event.
    `snakeboot.event_publication` keeps the offsets in the application's database.

    A stream that is deleted and declared anew counts from 0 again, so the position of its consumer is one of a stream
    that is gone, as a committed offset beyond the end of a Kafka topic is. The consumer that finds that out starts
    over (`start_over`), like Kafka's `auto.offset.reset=earliest`.
    """

    @abstractmethod
    def position(self, consumer: str) -> StreamPosition:
        """Returns how far `consumer` has read: its generation and the last event it handled."""

    @abstractmethod
    def claiming(self, consumer: str, event: StreamEvent, *, generation: int = 0) -> AbstractContextManager[bool]:
        """Claims `event` for `consumer` around the work that handles it, and tells whether to do that work.

        It yields False when `consumer` handled that event or a later one already, or started over since
        `generation`. The claim holds once the block ends without an exception, in the running transaction; another
        process that claims an offset of the same consumer meanwhile waits for it, and then finds the event handled.
        """

    @abstractmethod
    def start_over(self, consumer: str, seen: StreamPosition) -> bool:
        """Forgets the last event `consumer` handled and starts its next generation, when its position is still
        `seen`; returns whether it did. Of the processes that find the same stream gone, one starts over."""

    def last_handled(self, consumer: str) -> int | None:
        """Returns the offset of the last event `consumer` handled, or None when it handled none yet."""
        last = self.position(consumer).last
        return last.offset if last is not None else None


class InMemoryStreamOffsets(StreamOffsets):
    """Remembers the offsets as long as the process runs: an application without a database.

    Its projections live in memory too, so a consumer that starts reads the stream from the start again and builds
    them anew.
    """

    def __init__(self) -> None:
        self._positions: dict[str, StreamPosition] = {}
        self._lock = threading.Lock()

    @override
    def position(self, consumer: str) -> StreamPosition:
        with self._lock:
            return self._positions.get(consumer, StreamPosition())

    @override
    @contextmanager
    def claiming(self, consumer: str, event: StreamEvent, *, generation: int = 0) -> Iterator[bool]:
        claimed = self._is_ahead(consumer, event, generation)
        yield claimed
        if claimed:  # not reached when the work raised: the event is handled again
            with self._lock:
                if self._is_ahead_locked(consumer, event, generation):
                    self._positions[consumer] = StreamPosition(generation, event)

    @override
    def start_over(self, consumer: str, seen: StreamPosition) -> bool:
        with self._lock:
            if self._positions.get(consumer, StreamPosition()) != seen:
                return False
            self._positions[consumer] = StreamPosition(seen.generation + 1)
            return True

    def clear(self) -> None:
        """Forgets every offset, as a test that keeps its application does before the next test."""
        with self._lock:
            self._positions.clear()

    def _is_ahead(self, consumer: str, event: StreamEvent, generation: int) -> bool:
        with self._lock:
            return self._is_ahead_locked(consumer, event, generation)

    def _is_ahead_locked(self, consumer: str, event: StreamEvent, generation: int) -> bool:
        position = self._positions.get(consumer, StreamPosition())
        behind = position.last is None or position.last.offset < event.offset
        return position.generation == generation and behind
