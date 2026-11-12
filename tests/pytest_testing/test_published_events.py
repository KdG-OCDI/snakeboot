"""`PublishedEvents` keeps every event the application of a test published, like Spring's `ApplicationEvents`."""

from uuid import uuid4

import pytest

from snakeboot.boot.testing import TestApplication
from snakeboot.events import ApplicationEventPublisher
from snakeboot.testing import Autowired, PublishedEvents, application_test
from snakeboot.transaction import transactional
from tests.pytest_testing.parcels.parcels import ParcelsApplication, ParcelSent, SendParcel

parcels_test = application_test(application=ParcelsApplication)


@parcels_test
def test_every_event_is_kept_in_the_order_it_was_published(
    send_parcel: Autowired[SendParcel], events: Autowired[PublishedEvents]
) -> None:
    first = send_parcel.execute("ann")
    second = send_parcel.execute("bob")

    assert [event.parcel_id for event in events.of_type(ParcelSent)] == [first, second]
    assert len(events) == 2


@parcels_test
def test_an_event_counts_once_published_even_when_its_transaction_rolls_back(
    publisher: Autowired[ApplicationEventPublisher], events: Autowired[PublishedEvents]
) -> None:
    @transactional
    def publish_and_fail() -> None:
        publisher.publish(ParcelSent(uuid4(), "ann"))
        raise RuntimeError("The transaction rolls back.")

    with pytest.raises(RuntimeError):
        publish_and_fail()

    assert len(events.of_type(ParcelSent)) == 1


@parcels_test
class TestPublishedEventsOfATestClass:
    events: Autowired[PublishedEvents]
    send_parcel: Autowired[SendParcel]

    def test_clear_forgets_the_events_so_far(self) -> None:
        self.send_parcel.execute("ann")
        self.events.clear()

        self.send_parcel.execute("bob")

        assert [event.recipient for event in self.events.of_type(ParcelSent)] == ["bob"]

    def test_every_test_starts_without_events(self) -> None:
        assert list(self.events) == []


def test_a_test_application_keeps_the_events_of_its_application() -> None:
    with TestApplication.start(ParcelsApplication) as application:
        application.get(SendParcel).execute("ann")

        assert [event.recipient for event in application.published_events.of_type(ParcelSent)] == ["ann"]
        assert application.get(PublishedEvents) is application.published_events
