"""The table of the event publication registry, in snakeboot's own terms: an entity and its repository.

Every application with `[database]` maps it, but its table is part of the schema only once the application has an
`@application_module_listener` method: then `make_migration` writes it into the application's migrations, like the
schema Spring Modulith's JDBC registry asks for once its starter is there.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Protocol
from uuid import UUID

from snakeboot.data import Column, CrudRepository, Id, Index, LockMode, PageRequest, entity, lock
from snakeboot.events.event_listener_markers import APPLICATION_MODULE_LISTENER_ATTRIBUTE


@entity(
    "snakeboot_event_publication",
    indexes=(Index("snakeboot_event_publication_due_idx", "due_at"),),
    needed_by=APPLICATION_MODULE_LISTENER_ATTRIBUTE,
)
@dataclass
class EventPublicationRecord:
    """One event owed to one listener: the row of the transactional outbox.

    `due_at` is when it may be handed out again (a delivery lost meanwhile, or the next try after a failure);
    `attempts` counts the deliveries started; `last_failure` says why the last one failed. A delivered publication is
    deleted, so the table holds what is still owed.
    """

    publication_id: Annotated[UUID, Id()]
    listener_id: Annotated[str, Column(length=500)]
    event_type: Annotated[str, Column(length=500)]
    event: Any
    published_at: datetime
    due_at: datetime
    attempts: int
    last_failure: str | None = None


class EventPublicationRecords(CrudRepository[EventPublicationRecord, UUID], Protocol):
    """The publications not delivered yet."""

    @lock(LockMode.PESSIMISTIC_WRITE_SKIP_LOCKED)
    def find_by_due_at_less_than_equal_and_attempts_less_than_order_by_due_at_asc(
        self, now: datetime, attempts: int, page: PageRequest
    ) -> list[EventPublicationRecord]:
        """Locks the publications whose turn has come and that no other process locked, the longest waiting first."""
        ...
