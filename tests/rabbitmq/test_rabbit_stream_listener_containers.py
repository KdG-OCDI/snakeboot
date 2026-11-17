"""Every `@rabbit_stream_listener` method reads its stream from where it stopped, and never skips a message it could
not handle yet."""

import time
from collections.abc import Callable, Iterator

import pytest

from snakeboot.events import InMemoryStreamOffsets
from snakeboot.rabbitmq import (
    AmqpDeclarationError,
    InvalidRabbitListenerError,
    ListenerTiming,
    RabbitStreamListenerContainers,
)
from snakeboot.rabbitmq.rabbit_stream_listener_containers import rabbit_stream_listener_endpoints
from tests.rabbitmq.fake_broker import FakeBroker, FakeChannel
from tests.rabbitmq.sample_listeners.stream.listeners import BidProjection
from tests.rabbitmq.stand_ins import connection_factory_of
from tests.scheduling.stand_ins import CountingTaskDecorator, ScannedComponents

STREAM_PACKAGE = "tests.rabbitmq.sample_listeners.stream"
STREAM = "auctions.history"
CONSUMER = "tests.rabbitmq.sample_listeners.stream.listeners.BidProjection.on_bid"
QUICK = ListenerTiming(reconnect_seconds=0.01, retry_pause_seconds=0, poll_seconds=0.01, shutdown_seconds=2)
WAIT_SECONDS = 5


@pytest.fixture
def broker() -> FakeBroker:
    return FakeBroker()


@pytest.fixture
def projection() -> BidProjection:
    return BidProjection()


@pytest.fixture
def offsets() -> InMemoryStreamOffsets:
    return InMemoryStreamOffsets()


@pytest.fixture
def decorator() -> CountingTaskDecorator:
    return CountingTaskDecorator()


@pytest.fixture
def containers(
    broker: FakeBroker, projection: BidProjection, offsets: InMemoryStreamOffsets, decorator: CountingTaskDecorator
) -> Iterator[RabbitStreamListenerContainers]:
    components = ScannedComponents(STREAM_PACKAGE, projection)
    containers = RabbitStreamListenerContainers(
        lambda: rabbit_stream_listener_endpoints(components, decorator, offsets),
        connection_factory_of(broker),
        auto_startup=True,
        timing=QUICK,
    )
    yield containers
    containers.stop()


def bid(auction_id: str, amount: int = 10) -> bytes:
    return f'{{"auction_id": "{auction_id}", "amount": {amount}}}'.encode()


def deliver(broker: FakeBroker, body: bytes, offset: int, **headers: object) -> None:
    broker.deliver(STREAM, body, headers={"x-stream-offset": offset, **headers})


def settled(broker: FakeBroker) -> None:
    assert broker.settled.wait(WAIT_SECONDS), "the stream listener settled no message"


def eventually(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    while not condition():
        assert time.monotonic() < deadline, "the condition never held"
        time.sleep(0.01)


def reading_channels(broker: FakeBroker) -> list[FakeChannel]:
    return [channel for connection in broker.connections for channel in connection.channels if channel.consumers]


def test_declares_a_durable_topic_exchange_a_stream_and_the_binding(
    containers: RabbitStreamListenerContainers, broker: FakeBroker
) -> None:
    containers.start()
    eventually(lambda: bool(reading_channels(broker)))

    assert broker.exchanges == {"auctions": ("topic", True)}
    assert broker.queues == {STREAM: {"x-queue-type": "stream"}}
    assert broker.bindings == {(STREAM, "auctions", "auction.#")}
    assert [channel.prefetch for channel in reading_channels(broker)] == [100]


def test_a_listener_that_handled_nothing_reads_the_stream_from_its_start(
    containers: RabbitStreamListenerContainers, broker: FakeBroker
) -> None:
    containers.start()
    eventually(lambda: bool(reading_channels(broker)))

    [channel] = reading_channels(broker)
    assert channel.consumer_arguments[STREAM] == {"x-stream-offset": "first"}


def test_a_listener_reads_on_after_the_last_message_it_handled(
    containers: RabbitStreamListenerContainers, broker: FakeBroker, offsets: InMemoryStreamOffsets
) -> None:
    offsets.handled(CONSUMER, 41)

    containers.start()
    eventually(lambda: bool(reading_channels(broker)))

    [channel] = reading_channels(broker)
    assert channel.consumer_arguments[STREAM] == {"x-stream-offset": 42}


def test_a_message_is_handled_acknowledged_and_its_offset_saved(
    containers: RabbitStreamListenerContainers,
    broker: FakeBroker,
    projection: BidProjection,
    offsets: InMemoryStreamOffsets,
    decorator: CountingTaskDecorator,
) -> None:
    containers.start()
    deliver(broker, bid("a1", 120), offset=7)
    settled(broker)

    assert [(placed.auction_id, placed.amount) for placed in projection.bids] == [("a1", 120)]
    assert broker.acked == [1]
    assert offsets.last_handled(CONSUMER) == 7
    assert decorator.runs == 2  # where it reads on, then the message


def test_a_message_continues_the_trace_of_its_sender(
    containers: RabbitStreamListenerContainers, broker: FakeBroker, projection: BidProjection
) -> None:
    containers.start()
    sender = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    deliver(broker, bid("a1"), offset=0, traceparent=sender)
    settled(broker)

    assert projection.traces == ["4bf92f3577b34da6a3ce929d0e0e4736"]


@pytest.mark.parametrize(
    "body", [bid("refuse"), b"no json at all", b'{"auction_id": "a1"}'], ids=["refused", "no JSON", "not the model"]
)
def test_a_message_that_can_never_succeed_is_skipped_for_good(
    containers: RabbitStreamListenerContainers,
    broker: FakeBroker,
    projection: BidProjection,
    offsets: InMemoryStreamOffsets,
    body: bytes,
) -> None:
    containers.start()
    deliver(broker, body, offset=3)
    settled(broker)

    assert projection.bids == []
    assert broker.acked == [1]
    assert offsets.last_handled(CONSUMER) == 3


def test_a_failure_that_passes_is_only_a_delay(
    containers: RabbitStreamListenerContainers, broker: FakeBroker, projection: BidProjection
) -> None:
    containers.start()
    deliver(broker, bid("flaky"), offset=0)
    settled(broker)

    assert projection.attempts["flaky"] == 2
    assert [placed.auction_id for placed in projection.bids] == ["flaky"]


def test_a_message_that_keeps_failing_is_never_skipped_the_listener_reads_on_from_it(
    containers: RabbitStreamListenerContainers,
    broker: FakeBroker,
    projection: BidProjection,
    offsets: InMemoryStreamOffsets,
) -> None:
    offsets.handled(CONSUMER, 4)
    containers.start()
    deliver(broker, bid("crash"), offset=5)
    eventually(lambda: len(reading_channels(broker)) >= 2)

    assert projection.attempts["crash"] == 3
    assert broker.acked == []
    assert offsets.last_handled(CONSUMER) == 4
    assert reading_channels(broker)[1].consumer_arguments[STREAM] == {"x-stream-offset": 5}


def test_a_message_without_an_offset_is_acknowledged_and_not_handled(
    containers: RabbitStreamListenerContainers, broker: FakeBroker, projection: BidProjection
) -> None:
    containers.start()
    broker.deliver(STREAM, bid("a1"))
    settled(broker)

    assert projection.bids == []
    assert broker.acked == [1]


def test_a_stream_that_takes_the_name_of_a_classic_queue_stops_the_start_up(
    containers: RabbitStreamListenerContainers, broker: FakeBroker
) -> None:
    broker.queues[STREAM] = {}

    with pytest.raises(AmqpDeclarationError, match="cannot take the name of a classic queue"):
        containers.start()


def test_a_broker_that_is_down_does_not_stop_the_start_up(
    containers: RabbitStreamListenerContainers, broker: FakeBroker
) -> None:
    broker.unreachable_attempts = 2

    containers.start()
    eventually(lambda: bool(reading_channels(broker)))

    assert containers.running == 1


def test_without_auto_startup_no_listener_reads_but_a_broken_one_still_stops_the_start(broker: FakeBroker) -> None:
    containers = RabbitStreamListenerContainers(
        lambda: rabbit_stream_listener_endpoints(
            ScannedComponents(STREAM_PACKAGE), CountingTaskDecorator(), InMemoryStreamOffsets()
        ),
        connection_factory_of(broker),
        auto_startup=False,
        timing=QUICK,
    )

    with pytest.raises(InvalidRabbitListenerError, match="is no component"):
        containers.start()
    assert broker.connections == []


def test_an_application_without_stream_listeners_reads_nothing(broker: FakeBroker) -> None:
    containers = RabbitStreamListenerContainers(list, connection_factory_of(broker), auto_startup=True)

    containers.start()

    assert broker.connections == []
    assert containers.running == 0
