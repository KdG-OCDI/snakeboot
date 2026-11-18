"""The externalizer listens to the `@externalized` classes of the application, and to nothing in an application
without them."""

from dataclasses import dataclass
from typing import Any, override
from uuid import UUID

import pytest

from snakeboot.event_publication import PersistentEventPublicationRegistry
from snakeboot.events import (
    ApplicationEventPublisher,
    EventPublication,
    EventPublicationRegistry,
    InvalidApplicationEventListenerError,
    externalized,
)
from snakeboot.rabbitmq import EventExternalizer, RabbitTemplate

NAME = "snakeboot.rabbitmq.event_externalizer.EventExternalizer.externalize"


@externalized("auctions::auction.closed")
@dataclass(frozen=True)
class AuctionClosed:
    auction_id: str


class AuctionClosedLate(AuctionClosed):
    pass


@dataclass(frozen=True)
class AuctionOpened:
    auction_id: str


class NotJson:
    """An event the registry cannot keep as JSON."""


class RecordingTemplate(RabbitTemplate):
    def __init__(self) -> None:  # no broker
        self.sent: list[tuple[str, str, object, str | None]] = []

    @override
    def convert_and_send(
        self, exchange: str, routing_key: str, payload: object, *, message_id: str | None = None
    ) -> None:
        self.sent.append((exchange, routing_key, payload, message_id))


class OwingRegistry(EventPublicationRegistry):
    """Keeps every publication in memory, with a fixed identifier."""

    def __init__(self) -> None:
        self.stored: list[EventPublication] = []

    @override
    def verify(self, event_types: Any) -> None:
        pass

    @override
    def store(self, event: object, listener_ids: Any) -> list[EventPublication]:
        publications = [EventPublication(UUID(int=7), listener_id, event) for listener_id in listener_ids]
        self.stored.extend(publications)
        return publications

    @override
    def complete(self, publication: EventPublication) -> None:
        self.stored.remove(publication)

    @override
    def fail(self, publication: EventPublication, error: Exception) -> None:
        pass

    @override
    def claim_due(self) -> list[EventPublication]:
        return list(self.stored)

    @override
    def count_incomplete(self) -> int:
        return len(self.stored)


def test_an_externalizer_without_externalized_events_hears_nothing_and_is_owed_nothing() -> None:
    publisher = ApplicationEventPublisher([EventExternalizer.listening_to([], RecordingTemplate())])

    publisher.publish(AuctionClosed("a1"))

    assert not publisher.has_application_module_listeners


def test_the_externalizer_sends_the_externalized_events_and_their_subclasses() -> None:
    rabbit = RecordingTemplate()
    publisher = ApplicationEventPublisher([EventExternalizer.listening_to([AuctionClosed], rabbit)])

    publisher.publish(AuctionClosedLate("a1"))
    publisher.publish(AuctionOpened("a2"))  # not externalized

    [(exchange, routing_key, payload, message_id)] = rabbit.sent
    assert (exchange, routing_key, payload) == ("auctions", "auction.closed", AuctionClosedLate("a1"))
    assert message_id is not None
    assert publisher.has_application_module_listeners


def test_a_resent_event_keeps_the_message_id_of_its_publication() -> None:
    rabbit, registry = RecordingTemplate(), OwingRegistry()
    publisher = ApplicationEventPublisher([EventExternalizer.listening_to([AuctionClosed], rabbit)], registry=registry)
    registry.store(AuctionClosed("a1"), [NAME])

    publisher.resubmit_incomplete()

    assert [message_id for *_, message_id in rabbit.sent] == [str(UUID(int=7))]


def test_externalizers_of_two_applications_hear_each_their_own_events() -> None:
    first = EventExternalizer.listening_to([AuctionClosed], RecordingTemplate())
    second = EventExternalizer.listening_to([AuctionOpened], RecordingTemplate())

    assert getattr(type(first), "externalize") is not getattr(type(second), "externalize")  # noqa: B009  # reason: made per application, unknown to mypy


def test_an_externalized_event_the_registry_cannot_keep_stops_the_start() -> None:
    registry = PersistentEventPublicationRegistry(None)  # type: ignore[arg-type]  # verify reads no record
    externalizer = EventExternalizer.listening_to([NotJson], RecordingTemplate())

    with pytest.raises(InvalidApplicationEventListenerError, match="NotJson, or it is @externalized"):
        ApplicationEventPublisher([externalizer], registry=registry)


def test_the_listener_name_is_the_same_in_every_application() -> None:
    externalizer = EventExternalizer.listening_to([AuctionClosed], RecordingTemplate())

    assert f"{type(externalizer).__module__}.{type(externalizer).__qualname__}.externalize" == NAME
