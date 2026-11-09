"""Technical library: the event publication registry in the application's database, like Spring Modulith's.

    @application_event_listener
    class InvoiceOnOrderPlaced:
        @application_module_listener(OrderPlaced)        # own thread, own transaction, at least once
        def create_invoice(self, event: OrderPlaced) -> None: ...

With `[database]`, the transaction that publishes an event also writes one row per `@application_module_listener` into
`snakeboot_event_publication` (a transactional outbox); the listener's transaction deletes it. A publication whose
listener failed, or whose process stopped first, is delivered again, up to `max_attempts` times; then it waits in
the table, with its last failure, for a person. The optional table `[events]` sets the timing
(`PublicationTiming`). Run `make_migration` once to add the table to the application's migrations.

It knows `snakeboot.events`, `snakeboot.data`, the lifecycle and Pydantic's JSON, but no persistence framework.
"""

from snakeboot.event_publication.event_publication_record import EventPublicationRecord, EventPublicationRecords
from snakeboot.event_publication.event_publication_resubmitter import INCOMPLETE_METRIC, EventPublicationResubmitter
from snakeboot.event_publication.persistent_event_publication_registry import PersistentEventPublicationRegistry
from snakeboot.event_publication.publication_timing import (
    IN_FLIGHT,
    MAX_ATTEMPTS,
    RESUBMIT_EVERY,
    RETRY_AFTER,
    PublicationTiming,
)

__all__ = [
    "INCOMPLETE_METRIC",
    "IN_FLIGHT",
    "MAX_ATTEMPTS",
    "RESUBMIT_EVERY",
    "RETRY_AFTER",
    "EventPublicationRecord",
    "EventPublicationRecords",
    "EventPublicationResubmitter",
    "PersistentEventPublicationRegistry",
    "PublicationTiming",
]
