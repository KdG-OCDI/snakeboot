"""Every `@rabbit_stream_listener` method reads its stream from where it stopped, handles each message once, and never
skips a message it could not handle yet."""

import time
from collections.abc import Callable, Iterator

import pytest

from snakeboot.events import InMemoryStreamOffsets, StreamEvent, StreamPosition
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
QUICK = ListenerTiming(
    reconnect_seconds=0.01, retry_pause_seconds=0, poll_seconds=0.01, shutdown_seconds=2, stream_check_seconds=0.05
)
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


def handled(offsets: InMemoryStreamOffsets, offset: int) -> None:
    """As after reading the stream of the broker up to `offset`: its messages are bids on a0, a1, a2 and so on."""
    with offsets.claiming(CONSUMER, StreamEvent.of(offset, bid(f"a{offset}"))):
        pass


def stream_of(broker: FakeBroker, count: int, name: str = "a") -> None:
    """Appends `count` bids to the stream: on a0, a1, a2 and so on."""
    for index in range(count):
        broker.append(STREAM, bid(f"{name}{index}"))


def read(projection: BidProjection) -> list[str]:
    return [placed.auction_id for placed in projection.bids]


def bid(auction_id: str, amount: int = 10) -> bytes:
    return f'{{"auction_id": "{auction_id}", "amount": {amount}}}'.encode()


def deliver(broker: FakeBroker, body: bytes, offset: int, routing_key: str = "auction.bid", **headers: object) -> None:
    broker.deliver(STREAM, body, headers={"x-stream-offset": offset, **headers}, routing_key=routing_key)


def settled(broker: FakeBroker) -> None:
    assert broker.settled.wait(WAIT_SECONDS), "the stream listener settled no message"


def eventually(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    while not condition():
        assert time.monotonic() < deadline, "the condition never held"
        time.sleep(0.01)


def reading_channels(broker: FakeBroker) -> list[FakeChannel]:
    return [channel for connection in broker.connections for channel in connection.channels if channel.consumers]


def subscriptions(broker: FakeBroker) -> list[dict[str, object]]:
    """The arguments of every consumer the listener started, also of the ones RabbitMQ cancelled since."""
    return [
        channel.consumer_arguments[STREAM]
        for connection in broker.connections
        for channel in connection.channels
        if STREAM in channel.consumer_arguments
    ]


def test_declares_a_durable_topic_exchange_a_stream_and_the_binding(
    containers: RabbitStreamListenerContainers, broker: FakeBroker
) -> None:
    containers.start()
    eventually(lambda: bool(reading_channels(broker)))

    assert broker.exchanges == {"auctions": ("topic", True)}
    assert broker.queues == {STREAM: {"x-queue-type": "stream"}}
    assert broker.bindings == {(STREAM, "auctions", "auction.#")}
    assert [channel.prefetch for channel in reading_channels(broker)] == [100]


def test_a_stream_declared_with_a_retention_of_its_own_is_read_as_it_is(
    containers: RabbitStreamListenerContainers, broker: FakeBroker, projection: BidProjection
) -> None:
    broker.queues[STREAM] = {"x-queue-type": "stream", "x-max-age": "7D"}  # as RabbitMQ's definitions declared it

    containers.start()
    deliver(broker, bid("a1"), offset=0)
    settled(broker)

    assert broker.queues[STREAM] == {"x-queue-type": "stream", "x-max-age": "7D"}
    assert broker.bindings == {(STREAM, "auctions", "auction.#")}
    assert [placed.auction_id for placed in projection.bids] == ["a1"]


def test_a_listener_that_handled_nothing_reads_the_stream_from_its_start(
    containers: RabbitStreamListenerContainers, broker: FakeBroker
) -> None:
    containers.start()
    eventually(lambda: bool(reading_channels(broker)))
    time.sleep(4 * QUICK.stream_check_seconds)

    assert subscriptions(broker) == [{"x-stream-offset": "first"}]
    assert broker.looks == []  # it handled nothing, so no stream can be another one than it read


def test_a_listener_reads_on_after_the_last_message_it_handled(
    containers: RabbitStreamListenerContainers,
    broker: FakeBroker,
    projection: BidProjection,
    offsets: InMemoryStreamOffsets,
) -> None:
    stream_of(broker, 43)
    handled(offsets, 41)

    containers.start()
    eventually(lambda: read(projection) == ["a42"])

    assert subscriptions(broker) == [{"x-stream-offset": 41}]  # the last one again: it says which stream this is
    assert offsets.position(CONSUMER).generation == 0
    assert broker.looks == []


def test_a_listener_that_read_all_of_its_stream_waits_for_the_next_message(
    containers: RabbitStreamListenerContainers,
    broker: FakeBroker,
    projection: BidProjection,
    offsets: InMemoryStreamOffsets,
) -> None:
    stream_of(broker, 42)
    handled(offsets, 41)

    containers.start()
    eventually(lambda: bool(broker.acked))  # the last message it handled, again
    broker.append(STREAM, bid("a42"))
    eventually(lambda: read(projection) == ["a42"])

    assert offsets.position(CONSUMER).generation == 0


def test_a_stream_declared_anew_that_ends_before_the_last_message_handled_is_read_from_its_start(
    containers: RabbitStreamListenerContainers,
    broker: FakeBroker,
    projection: BidProjection,
    offsets: InMemoryStreamOffsets,
    caplog: pytest.LogCaptureFixture,
) -> None:
    handled(offsets, 1000)
    stream_of(broker, 50, "new")

    containers.start()
    eventually(lambda: len(projection.bids) == 50)

    assert read(projection) == [f"new{index}" for index in range(50)]
    assert offsets.position(CONSUMER) == StreamPosition(1, StreamEvent.of(49, bid("new49")))
    assert "up to offset 1000, but the stream ends at offset 49: it was deleted and declared anew" in caplog.text


def test_an_empty_stream_declared_anew_is_read_from_its_start(
    containers: RabbitStreamListenerContainers,
    broker: FakeBroker,
    projection: BidProjection,
    offsets: InMemoryStreamOffsets,
) -> None:
    handled(offsets, 1000)

    containers.start()
    eventually(lambda: offsets.position(CONSUMER) == StreamPosition(1))
    broker.append(STREAM, bid("new0"))
    eventually(lambda: read(projection) == ["new0"])


def test_a_stream_declared_anew_that_grew_beyond_the_last_message_handled_is_read_from_its_start(
    containers: RabbitStreamListenerContainers,
    broker: FakeBroker,
    projection: BidProjection,
    offsets: InMemoryStreamOffsets,
    caplog: pytest.LogCaptureFixture,
) -> None:
    handled(offsets, 10)
    stream_of(broker, 15, "new")

    containers.start()
    eventually(lambda: len(projection.bids) == 15)

    assert read(projection) == [f"new{index}" for index in range(15)]
    assert offsets.position(CONSUMER).generation == 1
    assert "the stream holds another message at offset 10" in caplog.text
    assert broker.looks == []  # the message at its offset told it


def test_a_stream_whose_retention_removed_old_messages_is_read_on(
    containers: RabbitStreamListenerContainers,
    broker: FakeBroker,
    projection: BidProjection,
    offsets: InMemoryStreamOffsets,
) -> None:
    stream_of(broker, 13)
    broker.retain_from(STREAM, 6)
    handled(offsets, 10)

    containers.start()
    eventually(lambda: read(projection) == ["a11", "a12"])

    assert offsets.position(CONSUMER).generation == 0


def test_a_retention_that_removed_what_the_listener_did_not_handle_yet_is_a_warning(
    containers: RabbitStreamListenerContainers,
    broker: FakeBroker,
    projection: BidProjection,
    offsets: InMemoryStreamOffsets,
    caplog: pytest.LogCaptureFixture,
) -> None:
    stream_of(broker, 20)
    broker.retain_from(STREAM, 15)
    handled(offsets, 10)

    containers.start()
    eventually(lambda: len(projection.bids) == 5)

    assert read(projection) == ["a15", "a16", "a17", "a18", "a19"]
    assert offsets.position(CONSUMER).generation == 0
    assert "up to offset 10, but the stream starts at offset 15 now" in caplog.text


def test_a_replica_that_is_behind_for_a_moment_is_no_other_stream(
    containers: RabbitStreamListenerContainers,
    broker: FakeBroker,
    projection: BidProjection,
    offsets: InMemoryStreamOffsets,
) -> None:
    stream_of(broker, 12)
    broker.behind[STREAM] = 5
    broker.caught_up_after_looks = 2  # the first look finds the stream ending at 5, the second finds all of it
    handled(offsets, 10)

    containers.start()
    eventually(lambda: read(projection) == ["a11"])

    assert offsets.position(CONSUMER).generation == 0
    assert broker.looks == [STREAM, STREAM]


def test_a_stream_deleted_and_declared_anew_while_the_listener_reads_is_read_from_its_start(
    containers: RabbitStreamListenerContainers,
    broker: FakeBroker,
    projection: BidProjection,
    offsets: InMemoryStreamOffsets,
) -> None:
    stream_of(broker, 3)
    containers.start()
    eventually(lambda: read(projection) == ["a0", "a1", "a2"])

    broker.delete_stream(STREAM)
    stream_of(broker, 2, "new")
    eventually(lambda: len(projection.bids) == 5)

    assert read(projection) == ["a0", "a1", "a2", "new0", "new1"]
    assert offsets.position(CONSUMER).generation == 1


def test_of_two_processes_that_find_a_new_stream_one_starts_over_and_each_message_is_handled_once(
    containers: RabbitStreamListenerContainers,
    broker: FakeBroker,
    projection: BidProjection,
    offsets: InMemoryStreamOffsets,
    decorator: CountingTaskDecorator,
) -> None:
    other = BidProjection()
    second = RabbitStreamListenerContainers(
        lambda: rabbit_stream_listener_endpoints(ScannedComponents(STREAM_PACKAGE, other), decorator, offsets),
        connection_factory_of(broker),
        auto_startup=True,
        timing=QUICK,
    )
    handled(offsets, 1000)
    stream_of(broker, 20, "new")

    containers.start()
    second.start()
    try:
        eventually(lambda: len(projection.bids) + len(other.bids) >= 20)
    finally:
        second.stop()

    assert sorted(read(projection) + read(other)) == sorted(f"new{index}" for index in range(20))
    assert offsets.position(CONSUMER).generation == 1


def test_a_message_is_handled_acknowledged_and_its_offset_claimed(
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


def test_a_message_another_process_handled_already_is_acknowledged_and_left_alone(
    containers: RabbitStreamListenerContainers,
    broker: FakeBroker,
    projection: BidProjection,
    offsets: InMemoryStreamOffsets,
) -> None:
    containers.start()
    eventually(lambda: bool(reading_channels(broker)))
    handled(offsets, 3)  # another process of the service read on meanwhile

    deliver(broker, bid("a1"), offset=3)
    settled(broker)

    assert projection.bids == []
    assert broker.acked == [1]


def test_a_message_the_routing_key_of_another_listener_put_in_the_stream_is_passed_over(
    containers: RabbitStreamListenerContainers,
    broker: FakeBroker,
    projection: BidProjection,
    offsets: InMemoryStreamOffsets,
) -> None:
    containers.start()
    deliver(broker, bid("a1"), offset=0, routing_key="payment.received")
    settled(broker)

    assert projection.bids == []
    assert broker.acked == [1]
    assert offsets.last_handled(CONSUMER) is None


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
    stream_of(broker, 5)
    broker.append(STREAM, bid("crash"))
    handled(offsets, 4)
    containers.start()
    eventually(lambda: len(subscriptions(broker)) >= 2)

    assert projection.attempts["crash"] >= 3
    assert projection.bids == []
    assert offsets.last_handled(CONSUMER) == 4
    assert subscriptions(broker)[1] == {"x-stream-offset": 4}


def test_a_listener_that_rabbitmq_stops_reading_subscribes_again(
    containers: RabbitStreamListenerContainers, broker: FakeBroker, offsets: InMemoryStreamOffsets
) -> None:
    containers.start()
    eventually(lambda: bool(reading_channels(broker)))
    handled(offsets, 9)

    broker.cancel_consumers(STREAM)  # as when the stream is deleted
    eventually(lambda: len(subscriptions(broker)) >= 2)

    assert subscriptions(broker)[1] == {"x-stream-offset": 9}


def test_a_message_without_an_offset_stays_where_it_is_and_the_listener_stops_reading(
    containers: RabbitStreamListenerContainers, broker: FakeBroker, projection: BidProjection
) -> None:
    containers.start()
    broker.deliver(STREAM, bid("a1"), routing_key="auction.bid")  # from a classic queue, which has no offsets
    eventually(lambda: len(subscriptions(broker)) >= 2)

    assert projection.bids == []
    assert broker.acked == []


def test_a_classic_queue_with_the_name_of_the_stream_stops_the_start_up(
    containers: RabbitStreamListenerContainers, broker: FakeBroker
) -> None:
    broker.queues[STREAM] = {}

    with pytest.raises(AmqpDeclarationError, match=r"the classic queue auctions\.history cannot become a stream"):
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
