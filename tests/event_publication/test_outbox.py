"""In a started application with a database, an `@application_module_listener` gets its event at least once: the
publication is written with the change that caused it, and stays until the listener's own transaction succeeded."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from snakeboot.boot.testing import TestApplication
from snakeboot.event_publication import MAX_ATTEMPTS, EventPublicationRecords
from snakeboot.events import ApplicationEventPublisher
from tests.event_publication.sample_outbox.orders import (
    InvoiceRecord,
    InvoiceRecords,
    InvoicingService,
    OrderRecords,
    PlaceOrderUseCase,
)
from tests.event_publication.sample_outbox.outbox_application import OutboxApplication

PLACED_AT = datetime(2026, 11, 9, 10, tzinfo=UTC)


@pytest.fixture
def application() -> Iterator[TestApplication]:
    with TestApplication.start(OutboxApplication) as started:
        yield started


def place(application: TestApplication, order_id: str) -> None:
    application.get(PlaceOrderUseCase).execute(order_id, 42, PLACED_AT)


def make_due(application: TestApplication) -> None:
    records = application.get(EventPublicationRecords)
    for record in records.find_all():
        record.due_at = datetime.now(UTC) - timedelta(seconds=1)
        records.save(record)


def test_the_listener_receives_the_event_and_no_publication_stays(application: TestApplication) -> None:
    place(application, "o1")

    assert application.get(InvoiceRecords).find_all() == [InvoiceRecord("o1", 42)]
    assert application.get(EventPublicationRecords).count() == 0


def test_a_failing_listener_rolls_back_its_own_work_and_not_the_order(application: TestApplication) -> None:
    application.get(InvoicingService).down = True

    place(application, "o1")

    assert application.get(OrderRecords).count() == 1
    assert application.get(InvoiceRecords).count() == 0


def test_a_failed_publication_stays_with_the_event_and_the_failure(application: TestApplication) -> None:
    application.get(InvoicingService).down = True

    place(application, "o1")

    [record] = application.get(EventPublicationRecords).find_all()
    assert record.listener_id.endswith(".InvoiceOnOrderPlaced.invoice")
    assert record.event_type == "tests.event_publication.sample_outbox.orders:OrderPlaced"
    assert record.event == {"order_id": "o1", "amount": 42, "placed_at": "2026-11-09T10:00:00Z"}
    assert (record.attempts, record.last_failure) == (1, "ConnectionError: the invoicing service is down")
    assert record.due_at > datetime.now(UTC)


def test_a_failed_publication_is_delivered_again_once_its_turn_has_come(application: TestApplication) -> None:
    service, publisher = application.get(InvoicingService), application.get(ApplicationEventPublisher)
    service.down = True
    place(application, "o1")
    service.down = False

    assert publisher.resubmit_incomplete() == 0
    make_due(application)
    assert publisher.resubmit_incomplete() == 1

    assert application.get(InvoiceRecords).find_all() == [InvoiceRecord("o1", 42)]
    assert application.get(EventPublicationRecords).count() == 0


def test_a_publication_that_keeps_failing_waits_for_a_person(application: TestApplication) -> None:
    application.get(InvoicingService).down = True
    place(application, "o1")
    publisher = application.get(ApplicationEventPublisher)

    for _ in range(MAX_ATTEMPTS + 2):
        make_due(application)
        publisher.resubmit_incomplete()

    [record] = application.get(EventPublicationRecords).find_all()
    assert record.attempts == MAX_ATTEMPTS
    assert record.last_failure == "ConnectionError: the invoicing service is down"
