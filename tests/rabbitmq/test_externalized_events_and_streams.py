"""An `@externalized` event reaches the broker through the outbox, and a stream listener builds a projection of it.

The application of a test sends without a broker, so the `InProcessRabbitTemplate` shows what RabbitMQ would get.
"""

from collections.abc import Iterator

import pytest

from snakeboot.boot.testing import TestApplication
from snakeboot.event_publication import (
    EventPublicationRecord,
    EventPublicationRecords,
    StreamOffsetRecord,
    StreamOffsetRecords,
)
from snakeboot.events import ApplicationEventPublisher, InvalidExternalizationError, StreamEvent, StreamOffsets
from snakeboot.lifecycle import ApplicationComponents, TaskDecorator
from snakeboot.rabbitmq import InProcessRabbitTemplate, RabbitTemplate, RejectAndDontRequeueError
from snakeboot.rabbitmq.rabbit_stream_listener_containers import (
    RabbitStreamListenerEndpoint,
    rabbit_stream_listener_endpoints,
)
from snakeboot.sqlalchemy_data.schema_entities import entities_of_the_schema
from tests.pytest_testing.parcels.parcels import ParcelsApplication
from tests.rabbitmq.sample_auctions.auctions import (
    AuctionClosed,
    AuctionsApplication,
    CloseAuction,
    ClosedAuctionProjection,
    ClosedAuctionRecord,
    ClosedAuctionRecords,
    PaymentProjection,
)
from tests.rabbitmq.sample_externalized_without_broker.auctions import AuctionsWithoutBrokerApplication

PROJECTION = "tests.rabbitmq.sample_auctions.auctions.ClosedAuctionProjection.on_auction_event"


@pytest.fixture
def application() -> Iterator[TestApplication]:
    with TestApplication.start(AuctionsApplication) as started:
        yield started


def sent(application: TestApplication) -> InProcessRabbitTemplate:
    rabbit = application.get(RabbitTemplate)
    assert isinstance(rabbit, InProcessRabbitTemplate)
    return rabbit


def test_an_externalized_event_goes_to_its_exchange_once_its_transaction_committed(
    application: TestApplication,
) -> None:
    application.get(CloseAuction).execute("a1", 120)

    [message] = sent(application).sent
    assert (message.exchange, message.routing_key) == ("auctions", "auction.closed")
    assert message.json() == {"auction_id": "a1", "winning_bid": 120}
    assert application.get(EventPublicationRecords).count() == 0


def test_an_externalized_event_carries_the_identifier_of_its_publication(application: TestApplication) -> None:
    application.get(CloseAuction).execute("a1", 120)

    [message] = sent(application).sent
    assert message.message_id is not None


def test_an_externalized_event_is_still_an_application_event(application: TestApplication) -> None:
    application.get(CloseAuction).execute("a1", 120)

    assert application.published_events.of_type(AuctionClosed) == [AuctionClosed("a1", 120)]


def test_the_event_of_a_transaction_that_rolls_back_is_not_sent(application: TestApplication) -> None:
    with pytest.raises(RuntimeError):
        application.get(CloseAuction).execute_and_fail("a1")

    assert sent(application).sent == []


def test_an_event_published_outside_a_transaction_is_sent_at_once(application: TestApplication) -> None:
    application.get(CloseAuction).execute_without_transaction("a1")

    assert [message.json()["auction_id"] for message in sent(application).sent] == ["a1"]


def test_a_stream_listener_builds_its_projection_and_saves_its_offset(application: TestApplication) -> None:
    close = application.get(CloseAuction)
    close.execute("a1", 120)
    close.execute("a2", 80)

    assert sorted(application.get(ClosedAuctionRecords).find_all(), key=lambda record: record.auction_id) == [
        ClosedAuctionRecord("a1", 120),
        ClosedAuctionRecord("a2", 80),
    ]
    record = application.get(StreamOffsetRecords).find_by_id(PROJECTION)
    assert record is not None
    assert (record.last_offset, record.generation) == (1, 0)
    assert record.fingerprint is not None  # which message that was, should the stream be declared anew


def test_what_a_stream_listener_refuses_is_kept_as_refused_and_skipped(application: TestApplication) -> None:
    application.get(CloseAuction).execute("a1", -1)

    [refused] = sent(application).refused
    assert refused.listener == PROJECTION
    assert isinstance(refused.error, RejectAndDontRequeueError)
    assert refused.dead_letter_queue is None
    assert application.get(StreamOffsets).last_handled(PROJECTION) == 0


def test_a_stream_listener_that_fails_stalls_as_it_would_on_rabbitmq(application: TestApplication) -> None:
    close = application.get(CloseAuction)
    close.execute("crash", 1)
    close.execute("a2", 80)

    [refused] = sent(application).refused
    assert (refused.listener, type(refused.error)) == (PROJECTION, RuntimeError)
    assert application.get(ClosedAuctionRecords).find_all() == []  # rolled back, and a2 waits behind it
    assert application.get(StreamOffsets).last_handled(PROJECTION) is None


def test_a_stream_listener_handles_only_what_its_routing_key_matches(application: TestApplication) -> None:
    rabbit = sent(application)
    rabbit.convert_and_send("auctions", "payment.received", {"amount": 120})
    application.get(CloseAuction).execute("a1", 120)

    assert application.get(PaymentProjection).heard == [{"amount": 120}]
    assert application.get(ClosedAuctionProjection).handled == 1
    assert application.get(StreamOffsets).last_handled(PROJECTION) == 1  # the payment took offset 0 of the stream


def stream_endpoint(application: TestApplication) -> RabbitStreamListenerEndpoint:
    """The projection's endpoint, as one process of the service builds it."""
    endpoints = rabbit_stream_listener_endpoints(
        application.get(ApplicationComponents), application.get(TaskDecorator), application.get(StreamOffsets)
    )
    return next(endpoint for endpoint in endpoints if endpoint.name == PROJECTION)


def test_of_two_processes_reading_the_stream_one_handles_each_message(application: TestApplication) -> None:
    first, second = stream_endpoint(application), stream_endpoint(application)
    body = b'{"auction_id": "a1", "winning_bid": 120}'

    first.receive(body, StreamEvent(0))
    second.receive(body, StreamEvent(0))

    assert application.get(ClosedAuctionProjection).handled == 1
    assert application.get(StreamOffsets).last_handled(PROJECTION) == 0


def test_a_failing_listener_rolls_back_its_projection_and_its_offset(application: TestApplication) -> None:
    endpoint = stream_endpoint(application)

    with pytest.raises(RuntimeError):
        endpoint.receive(b'{"auction_id": "crash", "winning_bid": 1}', StreamEvent(0))
    endpoint.receive(b'{"auction_id": "a1", "winning_bid": 120}', StreamEvent(0))  # the message is handled again

    assert application.get(ClosedAuctionRecords).find_all() == [ClosedAuctionRecord("a1", 120)]
    assert application.get(StreamOffsets).last_handled(PROJECTION) == 0


def test_the_streams_start_empty_again_after_a_reset(application: TestApplication) -> None:
    application.get(CloseAuction).execute("a1", 120)
    application.reset()
    application.resume()

    application.get(CloseAuction).execute("a2", 80)

    assert application.get(StreamOffsets).last_handled(PROJECTION) == 0


def test_a_listener_whose_offset_is_one_of_an_earlier_stream_starts_over(application: TestApplication) -> None:
    offsets = application.get(StreamOffsets)
    endpoint = stream_endpoint(application)
    endpoint.receive(b'{"auction_id": "a0", "winning_bid": 1}', StreamEvent(1000, "of the stream that is gone"))

    application.get(CloseAuction).execute("a1", 120)  # offset 0 of the test's own, empty stream

    assert ClosedAuctionRecord("a1", 120) in application.get(ClosedAuctionRecords).find_all()
    assert offsets.position(PROJECTION).generation == 1
    assert offsets.last_handled(PROJECTION) == 0


def test_the_outbox_and_the_offsets_are_part_of_the_schema(application: TestApplication) -> None:
    schema = entities_of_the_schema(application.get(ApplicationComponents))

    assert {EventPublicationRecord, StreamOffsetRecord} <= set(schema)


def test_an_application_without_externalized_events_is_owed_no_publication() -> None:
    with TestApplication.start(ParcelsApplication) as parcels:  # a database and a broker
        assert not parcels.get(ApplicationEventPublisher).has_application_module_listeners


def test_externalized_events_without_a_broker_stop_the_start() -> None:
    with pytest.raises(InvalidExternalizationError, match=r"AuctionClosed @externalized.*\[rabbitmq\]"):
        TestApplication.start(AuctionsWithoutBrokerApplication)
