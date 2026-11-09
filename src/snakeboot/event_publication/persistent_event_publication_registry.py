import functools
import uuid
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from importlib import import_module
from typing import Any, Final, override

from pydantic import PydanticSchemaGenerationError, TypeAdapter, ValidationError

from snakeboot.data import PageRequest
from snakeboot.event_publication.event_publication_record import EventPublicationRecord, EventPublicationRecords
from snakeboot.event_publication.publication_timing import PublicationTiming
from snakeboot.events import EventPublication, EventPublicationRegistry, InvalidApplicationEventListenerError
from snakeboot.transaction import transactional

CLAIM_BATCH: Final = 100
"""How many publications one resubmission takes at most."""

_FAILURE_LENGTH: Final = 2000


class PersistentEventPublicationRegistry(EventPublicationRegistry):
    """Keeps the publications in the application's database, like Spring Modulith's JDBC registry.

    A publication is a row of `snakeboot_event_publication`, written in the publisher's transaction with the event as
    JSON, and deleted in the listener's transaction. `claim_due` takes the rows whose turn has come with
    `FOR UPDATE SKIP LOCKED`, so the processes of a service share them out instead of delivering one twice. `timing`
    says how long a delivery may take, how long a failed one waits, and how many tries one gets.
    """

    def __init__(
        self,
        records: EventPublicationRecords,
        *,
        timing: PublicationTiming | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._records = records
        self._timing = timing or PublicationTiming()
        self._clock = clock or _now

    @override
    def verify(self, event_types: Iterable[type]) -> None:
        for event_type in event_types:
            try:
                _adapter(event_type)
            except PydanticSchemaGenerationError as error:
                raise InvalidApplicationEventListenerError(
                    f"An @application_module_listener receives {event_type.__qualname__}, which the event publication "
                    "registry cannot keep as JSON: make it a dataclass or a Pydantic model."
                ) from error

    @override
    def store(self, event: object, listener_ids: Sequence[str]) -> list[EventPublication]:
        now, event_type = self._clock(), type(event)
        content = _adapter(event_type).dump_python(event, mode="json")
        records = [
            EventPublicationRecord(
                publication_id=uuid.uuid4(),
                listener_id=listener_id,
                event_type=f"{event_type.__module__}:{event_type.__qualname__}",
                event=content,
                published_at=now,
                due_at=now + self._timing.in_flight,
                attempts=1,
            )
            for listener_id in listener_ids
        ]
        self._records.save_all(records)
        return [EventPublication(record.publication_id, record.listener_id, event) for record in records]

    @override
    def complete(self, publication: EventPublication) -> None:
        self._records.delete_by_id(publication.identifier)

    @override
    def fail(self, publication: EventPublication, error: Exception) -> None:
        record = self._records.find_by_id(publication.identifier)
        if record is None:
            return
        record.last_failure = f"{type(error).__qualname__}: {error}"[:_FAILURE_LENGTH]
        record.due_at = self._clock() + self._timing.retry_after * record.attempts
        self._records.save(record)

    @override
    @transactional
    def claim_due(self) -> list[EventPublication]:
        now = self._clock()
        due = self._records.find_by_due_at_less_than_equal_and_attempts_less_than_order_by_due_at_asc(
            now, self._timing.max_attempts, PageRequest(0, CLAIM_BATCH)
        )
        claimed = [publication for record in due if (publication := self._claimed(record, now)) is not None]
        self._records.save_all(due)
        return claimed

    @override
    def count_incomplete(self) -> int:
        return self._records.count()

    def _claimed(self, record: EventPublicationRecord, now: datetime) -> EventPublication | None:
        record.attempts += 1
        record.due_at = now + self._timing.in_flight
        try:
            event = _adapter(_type_named(record.event_type)).validate_python(record.event)
        except (LookupError, ValidationError, PydanticSchemaGenerationError) as error:
            # An event no class reads any more never will: it waits for a person, not for the next try.
            record.attempts = self._timing.max_attempts
            record.last_failure = f"The event cannot be read back: {error}"[:_FAILURE_LENGTH]
            return None
        return EventPublication(record.publication_id, record.listener_id, event)


_ADAPTERS: Final[dict[type, TypeAdapter[Any]]] = {}


def _adapter(event_type: type) -> TypeAdapter[Any]:
    # Building an adapter reads the whole class; the events of one type share one.
    adapter = _ADAPTERS.get(event_type)
    if adapter is None:
        adapter = _ADAPTERS[event_type] = TypeAdapter(event_type)
    return adapter


def _type_named(name: str) -> type:
    module_name, _, qualified_name = name.partition(":")
    try:
        found: object = functools.reduce(getattr, qualified_name.split("."), import_module(module_name))
    except (ImportError, AttributeError, ValueError) as error:
        raise LookupError(f"No class is named {name}.") from error
    if not isinstance(found, type):
        raise LookupError(f"{name} names no class.")
    return found


def _now() -> datetime:
    return datetime.now(UTC)
