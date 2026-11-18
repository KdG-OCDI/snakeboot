"""On RabbitMQ: a stream keeps every message, so a new consumer builds its projection from the whole history, and a
consumer that restarts reads on after the last message it handled.

Set SNAKEBOOT_TEST_RABBITMQ_URL to a broker on which these tests may declare and delete the stream `auctions.history`
and the exchange `auctions`, such as `docker run -p 55672:5672 rabbitmq:4-management`:

    SNAKEBOOT_TEST_RABBITMQ_URL=amqp://guest:guest@localhost:55672/%2F
"""

import os
import time
from collections.abc import Callable, Iterator
from typing import Any

import pika
import pytest

from snakeboot.events import InMemoryStreamOffsets
from snakeboot.rabbitmq import ListenerTiming, RabbitConnectionFactory, RabbitStreamListenerContainers, RabbitTemplate
from snakeboot.rabbitmq.rabbit_stream_listener_containers import rabbit_stream_listener_endpoints
from tests.rabbitmq.sample_listeners.stream.listeners import BidPlaced, BidProjection
from tests.rabbitmq.stand_ins import rabbit_properties
from tests.scheduling.stand_ins import CountingTaskDecorator, ScannedComponents

URL = os.environ.get("SNAKEBOOT_TEST_RABBITMQ_URL", "")

pytestmark = pytest.mark.skipif(not URL, reason="SNAKEBOOT_TEST_RABBITMQ_URL names no RabbitMQ")

STREAM_PACKAGE = "tests.rabbitmq.sample_listeners.stream"
STREAM = "auctions.history"
QUICK = ListenerTiming(reconnect_seconds=0.1, retry_pause_seconds=0, poll_seconds=0.05, shutdown_seconds=5)
WAIT_SECONDS = 10


def connection_factory() -> RabbitConnectionFactory:
    return RabbitConnectionFactory(
        rabbit_properties(), connect=lambda _: pika.BlockingConnection(pika.URLParameters(URL))
    )


@pytest.fixture
def channel() -> Iterator[Any]:
    connection = pika.BlockingConnection(pika.URLParameters(URL))
    channel = connection.channel()
    channel.queue_delete(STREAM)
    channel.exchange_delete("auctions")
    yield channel
    channel.queue_delete(STREAM)
    channel.exchange_delete("auctions")
    connection.close()


class Reader:
    """A projection and its offsets, read from the stream while it runs."""

    def __init__(self, offsets: InMemoryStreamOffsets) -> None:
        self.projection = BidProjection()
        components = ScannedComponents(STREAM_PACKAGE, self.projection)
        self._containers = RabbitStreamListenerContainers(
            lambda: rabbit_stream_listener_endpoints(components, CountingTaskDecorator(), offsets),
            connection_factory(),
            auto_startup=True,
            timing=QUICK,
        )

    def __enter__(self) -> "Reader":
        self._containers.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._containers.stop()

    def read(self) -> list[str]:
        return [placed.auction_id for placed in self.projection.bids]


def eventually(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    while not condition():
        assert time.monotonic() < deadline, "the condition never held"
        time.sleep(0.05)


def publish(*auction_ids: str) -> None:
    rabbit = RabbitTemplate(connection_factory())
    for auction_id in auction_ids:
        rabbit.convert_and_send("auctions", "auction.bid", BidPlaced(auction_id=auction_id, amount=10))


@pytest.mark.usefixtures("channel")
def test_a_new_consumer_reads_the_whole_history_and_a_restarted_one_reads_on() -> None:
    with Reader(InMemoryStreamOffsets()):
        pass  # declares the stream, which keeps every message from now on
    publish("a1", "a2", "a3")

    offsets = InMemoryStreamOffsets()
    with Reader(offsets) as first:
        eventually(lambda: first.read() == ["a1", "a2", "a3"])
        publish("a4")
        eventually(lambda: first.read() == ["a1", "a2", "a3", "a4"])

    publish("a5")
    with Reader(offsets) as restarted:
        eventually(lambda: restarted.read() == ["a5"])

    with Reader(InMemoryStreamOffsets()) as newcomer:
        eventually(lambda: newcomer.read() == ["a1", "a2", "a3", "a4", "a5"])


def test_a_stream_with_a_retention_of_its_own_and_another_binding_is_read_as_it_is(channel: Any) -> None:
    channel.exchange_declare("auctions", exchange_type="topic", durable=True)
    channel.queue_declare(STREAM, durable=True, arguments={"x-queue-type": "stream", "x-max-age": "7D"})
    channel.queue_bind(STREAM, "auctions", routing_key="payment.#")  # the binding of another listener
    rabbit = RabbitTemplate(connection_factory())
    rabbit.convert_and_send("auctions", "payment.received", {"auction_id": "p1", "amount": 10})

    with Reader(InMemoryStreamOffsets()) as reader:
        publish("a1")  # once the reader bound the stream with its own routing key
        eventually(lambda: reader.read() == ["a1"])

    assert reader.projection.attempts == {"a1": 1}  # the payment was passed over, not handled
