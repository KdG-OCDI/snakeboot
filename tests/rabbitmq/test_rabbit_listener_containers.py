"""Every `@rabbit_listener` method consumes its queue on a thread of its own, and settles messages as Spring does."""

from collections.abc import Iterator

import pytest

from snakeboot.rabbitmq import InvalidRabbitListenerError, ListenerTiming, RabbitListenerContainers
from tests.rabbitmq.fake_broker import FakeBroker
from tests.rabbitmq.sample_listeners.working.listeners import GameStartedListener
from tests.rabbitmq.stand_ins import connection_factory_of
from tests.scheduling.stand_ins import CountingTaskDecorator, ScannedComponents

WORKING = "tests.rabbitmq.sample_listeners.working"
QUEUE = "tictactoe.game-started"
QUICK = ListenerTiming(reconnect_seconds=0.01, retry_pause_seconds=0, poll_seconds=0.01, shutdown_seconds=2)
WAIT_SECONDS = 5


@pytest.fixture
def broker() -> FakeBroker:
    return FakeBroker()


@pytest.fixture
def listener() -> GameStartedListener:
    return GameStartedListener()


@pytest.fixture
def decorator() -> CountingTaskDecorator:
    return CountingTaskDecorator()


@pytest.fixture
def containers(
    broker: FakeBroker, listener: GameStartedListener, decorator: CountingTaskDecorator
) -> Iterator[RabbitListenerContainers]:
    containers = RabbitListenerContainers(
        ScannedComponents(WORKING, listener), decorator, connection_factory_of(broker), auto_startup=True, timing=QUICK
    )
    yield containers
    containers.stop()


def settled(broker: FakeBroker) -> None:
    assert broker.settled.wait(WAIT_SECONDS), "the listener settled no message"


def test_declares_a_durable_topic_exchange_a_durable_queue_and_the_binding(
    containers: RabbitListenerContainers, broker: FakeBroker, listener: GameStartedListener
) -> None:
    containers.start()
    broker.deliver(QUEUE, b'{"session_id": "s1", "player_ids": ["ann", "bob"]}')
    settled(broker)

    assert broker.exchanges == {"games": ("topic", True)}
    assert broker.queues == {QUEUE}
    assert broker.bindings == [(QUEUE, "games", "game.tictactoe.started")]
    assert broker.connections[0].channels[0].prefetch == 1


def test_a_message_becomes_the_model_the_method_takes_and_is_acknowledged(
    containers: RabbitListenerContainers, broker: FakeBroker, listener: GameStartedListener
) -> None:
    containers.start()
    broker.deliver(QUEUE, b'{"session_id": "s1", "player_ids": ["ann", "bob"]}')
    settled(broker)

    assert [game.session_id for game in listener.started] == ["s1"]
    assert broker.acked == [1]


def test_a_message_continues_the_trace_of_its_sender(
    containers: RabbitListenerContainers, broker: FakeBroker, listener: GameStartedListener
) -> None:
    containers.start()
    sender = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    broker.deliver(QUEUE, b'{"session_id": "s1", "player_ids": []}', headers={"traceparent": sender})
    settled(broker)

    assert listener.traces == ["4bf92f3577b34da6a3ce929d0e0e4736"]


def test_every_message_goes_through_the_task_decorator(
    containers: RabbitListenerContainers, broker: FakeBroker, decorator: CountingTaskDecorator
) -> None:
    containers.start()
    broker.deliver(QUEUE, b'{"session_id": "s1", "player_ids": ["ann", "bob"]}')
    settled(broker)

    assert decorator.runs == 1


@pytest.mark.parametrize(
    "body",
    [b'{"session_id": "refuse", "player_ids": []}', b"no json at all", b'{"session_id": "s1"}'],
    ids=["refused by the listener", "no JSON", "not the model"],
)
def test_a_message_that_can_never_succeed_is_refused_for_good(
    containers: RabbitListenerContainers, broker: FakeBroker, body: bytes
) -> None:
    containers.start()
    broker.deliver(QUEUE, body)
    settled(broker)

    assert broker.rejected == [(1, False)]


def test_a_message_whose_handling_keeps_failing_is_tried_three_times_then_refused_for_good(
    containers: RabbitListenerContainers, broker: FakeBroker, listener: GameStartedListener
) -> None:
    containers.start()
    broker.deliver(QUEUE, b'{"session_id": "crash", "player_ids": []}')
    settled(broker)

    assert listener.attempts["crash"] == 3
    assert broker.rejected == [(1, False)]


def test_a_failure_that_passes_is_only_a_delay(
    containers: RabbitListenerContainers, broker: FakeBroker, listener: GameStartedListener
) -> None:
    containers.start()
    broker.deliver(QUEUE, b'{"session_id": "flaky", "player_ids": []}')
    settled(broker)

    assert listener.attempts["flaky"] == 2
    assert broker.acked == [1]


def test_a_message_that_failed_once_is_not_lost_when_the_application_stops(
    broker: FakeBroker, listener: GameStartedListener, decorator: CountingTaskDecorator
) -> None:
    patient = ListenerTiming(retry_pause_seconds=30, poll_seconds=0.01, shutdown_seconds=2)
    containers = RabbitListenerContainers(
        ScannedComponents(WORKING, listener),
        decorator,
        connection_factory_of(broker),
        auto_startup=True,
        timing=patient,
    )
    containers.start()
    broker.deliver(QUEUE, b'{"session_id": "crash", "player_ids": []}')
    while listener.attempts.get("crash", 0) == 0:
        pass

    containers.stop()

    assert broker.rejected == [(1, True)]


def test_a_listener_waits_for_a_broker_that_is_down(
    broker: FakeBroker, listener: GameStartedListener, decorator: CountingTaskDecorator
) -> None:
    broker.unreachable_attempts = 2
    containers = RabbitListenerContainers(
        ScannedComponents(WORKING, listener), decorator, connection_factory_of(broker), auto_startup=True, timing=QUICK
    )

    containers.start()
    broker.deliver(QUEUE, b'{"session_id": "s1", "player_ids": ["ann", "bob"]}')
    try:
        assert listener.received.wait(WAIT_SECONDS)
    finally:
        containers.stop()


def test_stop_ends_every_listener(containers: RabbitListenerContainers, broker: FakeBroker) -> None:
    containers.start()
    assert containers.running == 1

    containers.stop()

    assert containers.running == 0


def test_with_auto_startup_off_nothing_consumes(
    broker: FakeBroker, listener: GameStartedListener, decorator: CountingTaskDecorator
) -> None:
    containers = RabbitListenerContainers(
        ScannedComponents(WORKING, listener), decorator, connection_factory_of(broker), auto_startup=False
    )

    containers.start()

    assert containers.running == 0
    assert broker.connections == []


def test_a_listener_of_a_class_that_is_no_component_stops_the_start_up(
    broker: FakeBroker, decorator: CountingTaskDecorator
) -> None:
    containers = RabbitListenerContainers(
        ScannedComponents(WORKING), decorator, connection_factory_of(broker), auto_startup=False
    )

    with pytest.raises(InvalidRabbitListenerError, match="GameStartedListener is no component: add @injectable"):
        containers.start()


@pytest.mark.parametrize(
    ("module", "message"),
    [
        ("asynchronous", "is async"),
        ("two_arguments", "must take exactly one argument"),
        ("takes_text", "takes a pydantic model, a dict or bytes"),
    ],
)
def test_a_listener_that_cannot_receive_stops_the_start_up(
    broker: FakeBroker, decorator: CountingTaskDecorator, module: str, message: str
) -> None:
    components = ScannedComponents(f"tests.rabbitmq.sample_listeners.broken.{module}")
    containers = RabbitListenerContainers(components, decorator, connection_factory_of(broker), auto_startup=True)

    with pytest.raises(InvalidRabbitListenerError, match=message):
        containers.start()


def test_an_application_without_listeners_starts_and_connects_to_nothing(
    broker: FakeBroker, decorator: CountingTaskDecorator
) -> None:
    components = ScannedComponents("tests.component_scan.sample_project")
    containers = RabbitListenerContainers(components, decorator, connection_factory_of(broker), auto_startup=True)

    containers.start()

    assert containers.running == 0
    assert broker.connections == []
