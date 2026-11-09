from dataclasses import dataclass
from datetime import timedelta
from typing import Final, Self

from snakeboot.configuration import EventsProperties

RESUBMIT_EVERY: Final = timedelta(seconds=30)
"""How often the registry is asked for the publications whose turn has come."""

IN_FLIGHT: Final = timedelta(minutes=5)
"""How long a delivery may take: a publication still owed by then was lost (its process stopped) and goes out again."""

RETRY_AFTER: Final = timedelta(seconds=30)
"""How long a failed publication waits before the next try, times the tries so far: 30 seconds, 1 minute, ..."""

MAX_ATTEMPTS: Final = 10
"""How many deliveries a publication gets; after that it stays in the table, with its last failure, for a person."""


@dataclass(frozen=True, slots=True)
class PublicationTiming:
    """When the event publication registry delivers again: `[events]`, or snakeboot's own timing without it."""

    resubmit_every: timedelta = RESUBMIT_EVERY
    in_flight: timedelta = IN_FLIGHT
    retry_after: timedelta = RETRY_AFTER
    max_attempts: int = MAX_ATTEMPTS

    @classmethod
    def of(cls, properties: EventsProperties | None) -> Self:
        """Returns the timing `[events]` sets, or the default one when the application has no such table."""
        if properties is None:
            return cls()
        return cls(properties.resubmit_every, properties.in_flight, properties.retry_after, properties.max_attempts)
