"""The registry refuses at start-up what it cannot keep, gives up on what it cannot read back, and resubmits on a
thread of its own while the application runs."""

import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import override

import pytest

from snakeboot.actuator import MeterRegistry
from snakeboot.boot.testing import TestApplication
from snakeboot.event_publication import (
    INCOMPLETE_METRIC,
    MAX_ATTEMPTS,
    EventPublicationRecord,
    EventPublicationRecords,
    EventPublicationResubmitter,
    PersistentEventPublicationRegistry,
)
from snakeboot.events import ApplicationEventPublisher, InvalidApplicationEventListenerError
from snakeboot.sqlalchemy_data.schema_migrations import LOCATION, migration_locations
from tests.event_publication.sample_outbox.orders import InvoiceRecord, InvoicingService, PlaceOrderUseCase
from tests.event_publication.sample_outbox.outbox_application import OutboxApplication


class Unserializable:
    """No dataclass and no model: Pydantic cannot tell what JSON it is."""

    def __init__(self, lock: threading.Lock) -> None:
        self.lock = lock


@pytest.fixture
def application() -> Iterator[TestApplication]:
    with TestApplication.start(OutboxApplication) as started:
        yield started


def test_an_event_type_the_registry_cannot_keep_stops_the_start(application: TestApplication) -> None:
    registry = PersistentEventPublicationRegistry(application.get(EventPublicationRecords))

    with pytest.raises(
        InvalidApplicationEventListenerError,
        match="receives Unserializable, which the event publication registry cannot keep",
    ):
        registry.verify([Unserializable])


def test_an_event_no_class_reads_any_more_waits_for_a_person(application: TestApplication) -> None:
    application.get(InvoicingService).down = True
    application.get(PlaceOrderUseCase).execute("o1", 42, datetime(2026, 11, 9, tzinfo=UTC))
    records = application.get(EventPublicationRecords)
    [record] = records.find_all()
    record.event_type, record.due_at = "myapp.gone:OrderPlaced", datetime.now(UTC) - timedelta(seconds=1)
    records.save(record)

    assert application.get(ApplicationEventPublisher).resubmit_incomplete() == 0

    [record] = records.find_all()
    assert record.attempts == MAX_ATTEMPTS
    assert record.last_failure is not None
    assert record.last_failure.startswith("The event cannot be read back: No class is named myapp.gone:OrderPlaced")


def test_the_resubmitter_resubmits_at_start_and_shows_what_is_owed(application: TestApplication) -> None:
    application.get(InvoicingService).down = True
    application.get(PlaceOrderUseCase).execute("o1", 42, datetime(2026, 11, 9, tzinfo=UTC))
    application.get(InvoicingService).down = False
    records = application.get(EventPublicationRecords)
    [record] = records.find_all()
    record.due_at = datetime.now(UTC) - timedelta(seconds=1)
    records.save(record)
    meters = MeterRegistry()
    resubmitter = EventPublicationResubmitter(
        application.get(ApplicationEventPublisher),
        PersistentEventPublicationRegistry(records),
        meters,
    )

    resubmitter.start()
    try:
        assert f"{INCOMPLETE_METRIC} " in meters.scrape()
        for _ in range(200):
            if records.count() == 0:
                break
            threading.Event().wait(0.01)
    finally:
        resubmitter.stop()

    assert records.count() == 0
    assert not resubmitter.running


def test_the_resubmitter_starts_nothing_without_module_listeners() -> None:
    class Unused(PersistentEventPublicationRegistry):
        @override
        def claim_due(self) -> list[object]:  # type: ignore[override]
            raise AssertionError("nothing may be asked")

    resubmitter = EventPublicationResubmitter(
        ApplicationEventPublisher([]),
        Unused(records=None),  # type: ignore[arg-type]
        MeterRegistry(),
    )

    resubmitter.start()

    assert not resubmitter.running
    resubmitter.stop()


def test_the_registry_s_table_is_written_into_the_application_s_migrations() -> None:
    locations = migration_locations([EventPublicationRecord, InvoiceRecord])

    assert locations == [Path(__file__).parent / "sample_outbox" / LOCATION]
