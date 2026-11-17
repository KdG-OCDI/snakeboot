"""An `@externalized` event reaches the broker through the outbox, and a stream listener builds a projection of it.

The application of a test sends without a broker, so the `InProcessRabbitTemplate` shows what RabbitMQ would get.
"""

from collections.abc import Iterator

import pytest

from snakeboot.boot.testing import TestApplication
from snakeboot.event_publication import EventPublicationRecord, EventPublicationRecords, StreamOffsetRecord
from snakeboot.event_publication.stream_offset_record import StreamOffsetRecords
from snakeboot.lifecycle import ApplicationComponents
from snakeboot.rabbitmq import InProcessRabbitTemplate, RabbitTemplate, RejectAndDontRequeueError
from snakeboot.sqlalchemy_data.schema_entities import entities_of_the_schema
from tests.rabbitmq.sample_auctions.auctions import (
    AuctionClosed,
    AuctionsApplication,
    CloseAuction,
    ClosedAuctionRecord,
    ClosedAuctionRecords,
)

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
    assert application.get(StreamOffsetRecords).find_by_id(PROJECTION) == StreamOffsetRecord(PROJECTION, 1)


def test_what_a_stream_listener_refuses_is_kept_as_refused(application: TestApplication) -> None:
    application.get(CloseAuction).execute("a1", -1)

    [refused] = sent(application).refused
    assert refused.listener == PROJECTION
    assert isinstance(refused.error, RejectAndDontRequeueError)
    assert refused.dead_letter_queue is None


def test_the_streams_start_empty_again_after_a_reset(application: TestApplication) -> None:
    application.get(CloseAuction).execute("a1", 120)
    application.reset()
    application.resume()

    application.get(CloseAuction).execute("a2", 80)

    assert application.get(StreamOffsetRecords).find_by_id(PROJECTION) == StreamOffsetRecord(PROJECTION, 0)


def test_the_outbox_and_the_offsets_are_part_of_the_schema(application: TestApplication) -> None:
    schema = entities_of_the_schema(application.get(ApplicationComponents))

    assert {EventPublicationRecord, StreamOffsetRecord} <= set(schema)
