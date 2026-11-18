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
QUICK = ListenerTiming(
    reconnect_seconds=0.1, retry_pause_seconds=0, poll_seconds=0.05, shutdown_seconds=5, stream_check_seconds=0.5
)
CONSUMER = "tests.rabbitmq.sample_listeners.stream.listeners.BidProjection.on_bid"
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
    assert offsets.position(CONSUMER).generation == 0  # the same stream: it never started over

    with Reader(InMemoryStreamOffsets()) as newcomer:
        eventually(lambda: newcomer.read() == ["a1", "a2", "a3", "a4", "a5"])


def test_a_consumer_that_read_all_of_its_stream_reads_on_without_starting_over() -> None:
    declare_the_stream()
    publish("a1", "a2")
    offsets = read_up_to("a1", "a2")

    with Reader(offsets) as restarted:
        time.sleep(4 * QUICK.stream_check_seconds)  # nothing new: it waits, and has no doubt about its stream
        publish("a3")
        eventually(lambda: restarted.read() == ["a3"])

    assert offsets.position(CONSUMER).generation == 0


def declare_the_stream() -> None:
    with Reader(InMemoryStreamOffsets()):
        pass  # declares the stream, which keeps every message from now on


def read_up_to(*auction_ids: str) -> InMemoryStreamOffsets:
    """The offsets of a consumer that read the stream as it is now, and stopped."""
    offsets = InMemoryStreamOffsets()
    with Reader(offsets) as reader:
        eventually(lambda: reader.read() == list(auction_ids))
    return offsets


def test_a_shorter_stream_declared_anew_is_read_from_its_start(channel: Any) -> None:
    declare_the_stream()
    publish("a1", "a2", "a3")
    offsets = read_up_to("a1", "a2", "a3")

    channel.queue_delete(STREAM)
    declare_the_stream()
    publish("b1")

    with Reader(offsets) as reader:
        eventually(lambda: reader.read() == ["b1"])
        publish("b2")
        eventually(lambda: reader.read() == ["b1", "b2"])
    assert offsets.position(CONSUMER).generation == 1


def test_an_empty_stream_declared_anew_is_read_from_its_start(channel: Any) -> None:
    declare_the_stream()
    publish("a1", "a2", "a3")
    offsets = read_up_to("a1", "a2", "a3")

    channel.queue_delete(STREAM)

    with Reader(offsets) as reader:  # declares it anew, empty
        eventually(lambda: offsets.position(CONSUMER).generation == 1)
        publish("b1")
        eventually(lambda: reader.read() == ["b1"])


def test_a_stream_declared_anew_that_grew_beyond_the_last_message_handled_is_read_from_its_start(
    channel: Any,
) -> None:
    declare_the_stream()
    publish("a1", "a2")
    offsets = read_up_to("a1", "a2")

    channel.queue_delete(STREAM)
    declare_the_stream()
    publish("b1", "b2", "b3", "b4")

    with Reader(offsets) as reader:
        eventually(lambda: reader.read() == ["b1", "b2", "b3", "b4"])
    assert offsets.position(CONSUMER).generation == 1


def test_a_stream_deleted_and_declared_anew_while_the_consumer_reads_is_read_from_its_start(channel: Any) -> None:
    declare_the_stream()
    publish("a1", "a2", "a3")
    offsets = InMemoryStreamOffsets()

    with Reader(offsets) as reader:
        eventually(lambda: reader.read() == ["a1", "a2", "a3"])
        channel.queue_delete(STREAM)
        eventually(lambda: offsets.position(CONSUMER).generation == 1)  # it declared the stream anew, and looked
        publish("b1")
        eventually(lambda: reader.read() == ["a1", "a2", "a3", "b1"])


def test_a_stream_answers_a_consumer_as_the_stand_ins_of_the_other_tests_do(channel: Any) -> None:
    """What the check for a new stream relies on, and what `FakeBroker` imitates."""
    declare_the_stream()
    publish("a1", "a2", "a3")  # offsets 0, 1 and 2

    assert offsets_read_from(1) == [1, 2]  # none before the offset asked for
    assert offsets_read_from(7, publish_meanwhile="a4") == []  # beyond the end: not even what is written next
    assert offsets_read_from("last") == [3]
    # The count is right a moment later only, so the check does not take none counted for an empty stream.
    eventually(lambda: channel.queue_declare(STREAM, passive=True).method.message_count == 4)


def offsets_read_from(start: int | str, publish_meanwhile: str | None = None) -> list[int]:
    connection = pika.BlockingConnection(pika.URLParameters(URL))
    reading = connection.channel()
    reading.basic_qos(prefetch_count=100)
    read: list[int] = []
    reading.basic_consume(
        STREAM,
        lambda _channel, _delivery, properties, _body: read.append(properties.headers["x-stream-offset"]),
        arguments={"x-stream-offset": start},
    )
    if publish_meanwhile is not None:
        publish(publish_meanwhile)
    connection.process_data_events(time_limit=1)
    connection.process_data_events(time_limit=1)
    connection.close()
    return read


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
