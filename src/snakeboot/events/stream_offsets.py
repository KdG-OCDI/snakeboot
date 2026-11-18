import threading
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Final, override

STREAM_CONSUMER_ATTRIBUTE: Final = "__snakeboot_stream_consumer__"
"""The mark a stream listener leaves on its method: the table of the stream offsets is needed by it."""


class StreamOffsets(ABC):
    """How far each consumer of a stream of events has read, like the offsets Kafka commits for a consumer group.

    A stream keeps every event, so a consumer chooses where it reads from: from the start, to build its projection of
    the events from their history, and afterwards from the event after the last one it handled. The consumer claims
    the offset of an event for the work that handles it, so after a restart it neither skips an event nor handles
    one twice, and of the processes of one service that all read the stream, one handles each event.
    `snakeboot.event_publication` keeps the offsets in the application's database.
    """

    @abstractmethod
    def last_handled(self, consumer: str) -> int | None:
        """Returns the offset of the last event `consumer` handled, or None when it handled none yet."""

    @abstractmethod
    def claiming(self, consumer: str, offset: int) -> AbstractContextManager[bool]:
        """Claims `offset` for `consumer` around the work that handles its event, and tells whether to do that work.

        It yields False when `consumer` handled that event or a later one already. The claim holds once the block
        ends without an exception, in the running transaction; another process that claims an offset of the same
        consumer meanwhile waits for it, and then finds the event handled.
        """


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
    @contextmanager
    def claiming(self, consumer: str, offset: int) -> Iterator[bool]:
        last = self.last_handled(consumer)
        claimed = last is None or last < offset
        yield claimed
        if claimed:  # not reached when the work raised: the event is handled again
            with self._lock:
                self._offsets[consumer] = max(offset, self._offsets.get(consumer, offset))

    def clear(self) -> None:
        """Forgets every offset, as a test that keeps its application does before the next test."""
        with self._lock:
            self._offsets.clear()
