import threading
from abc import ABC, abstractmethod
from typing import Final, override

STREAM_CONSUMER_ATTRIBUTE: Final = "__snakeboot_stream_consumer__"
"""The mark a stream listener leaves on its method: the table of the stream offsets is needed by it."""


class StreamOffsets(ABC):
    """How far each consumer of a stream of events has read, like the offsets Kafka commits for a consumer group.

    A stream keeps every event, so a consumer chooses where it reads from: from the start, to build its projection of
    the events from their history, and afterwards from the event after the last one it handled. The consumer saves
    the offset of an event in the transaction that handled it, so after a restart it neither skips an event nor
    handles one twice. `snakeboot.event_publication` keeps the offsets in the application's database.
    """

    @abstractmethod
    def last_handled(self, consumer: str) -> int | None:
        """Returns the offset of the last event `consumer` handled, or None when it handled none yet."""

    @abstractmethod
    def handled(self, consumer: str, offset: int) -> None:
        """Remembers, in the running transaction, that `consumer` handled the event at `offset`."""


class InMemoryStreamOffsets(StreamOffsets):
    """Remembers the offsets as long as the process runs: an application without a database.

    Its projections live in memory too, so a consumer that starts reads the stream from the start again and builds
    them anew.
    """

    def __init__(self) -> None:
        self._offsets: dict[str, int] = {}
        self._lock = threading.Lock()

    @override
    def last_handled(self, consumer: str) -> int | None:
        with self._lock:
            return self._offsets.get(consumer)

    @override
    def handled(self, consumer: str, offset: int) -> None:
        with self._lock:
            self._offsets[consumer] = offset

    def clear(self) -> None:
        """Forgets every offset, as a test that keeps its application does before the next test."""
        with self._lock:
            self._offsets.clear()
