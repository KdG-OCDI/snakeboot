from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class EventPublication:
    """One event owed to one `@application_module_listener`, as the event publication registry keeps it."""

    identifier: UUID
    listener_id: str
    event: object


class EventPublicationRegistry(ABC):
    """Keeps every event owed to an `@application_module_listener` until it was delivered, like Spring Modulith's
    `EventPublicationRegistry`: the transactional outbox of the application's events.

    The publisher stores the publications in its own transaction, so they exist exactly when the change that caused
    them committed. The listener's transaction completes its publication; a failed or a lost delivery stays, and the
    registry hands it out again when its turn comes. `snakeboot.event_publication` keeps them in the application's
    database.
    """

    @abstractmethod
    def verify(self, event_types: Iterable[type]) -> None:
        """Raises at start-up when the registry cannot keep events of one of `event_types`."""

    @abstractmethod
    def store(self, event: object, listener_ids: Sequence[str]) -> list[EventPublication]:
        """Keeps `event` once for each listener, in the running transaction, and returns the publications."""

    @abstractmethod
    def complete(self, publication: EventPublication) -> None:
        """Forgets `publication`, in the listener's transaction: it was delivered."""

    @abstractmethod
    def fail(self, publication: EventPublication, error: Exception) -> None:
        """Remembers that delivering `publication` failed with `error`, so it is delivered again later."""

    @abstractmethod
    def claim_due(self) -> list[EventPublication]:
        """Takes the publications whose turn has come again: failed ones, and ones whose delivery was lost.

        A publication claimed here is not handed to another process until its delivery could have finished.
        """

    @abstractmethod
    def count_incomplete(self) -> int:
        """Returns how many publications are not delivered yet."""
