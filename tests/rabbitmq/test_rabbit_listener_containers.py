"""Every `@rabbit_listener` method consumes its queue on a thread of its own, and settles messages as Spring does."""

import time
from collections.abc import Iterator
from itertools import islice

import pytest

from snakeboot.rabbitmq import (
    AmqpDeclarationError,
    InvalidRabbitListenerError,
    ListenerTiming,
    RabbitListenerContainers,
)
from tests.rabbitmq.fake_broker import FakeBroker, FakeChannel
from tests.rabbitmq.sample_listeners.dead_letter.listeners import GameFinishedListener
from tests.rabbitmq.sample_listeners.working.listeners import GameStartedListener
from tests.rabbitmq.stand_ins import connection_factory_of
from tests.scheduling.stand_ins import CountingTaskDecorator, ScannedComponents

WORKING = "tests.rabbitmq.sample_listeners.working"
DEAD_LETTER = "tests.rabbitmq.sample_listeners.dead_letter"
QUEUE = "tictactoe.game-started"
FINISHED_QUEUE = "platform.game-finished"
DEAD_LETTER_QUEUE = "platform.game-finished.dead-letter"
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


def consuming_channels(broker: FakeBroker) -> list[FakeChannel]:
    return [channel for connection in broker.connections for channel in connection.channels if channel.consumers]


def test_declares_a_durable_topic_exchange_a_durable_queue_and_the_binding(
    containers: RabbitListenerContainers, broker: FakeBroker, listener: GameStartedListener
) -> None:
    containers.start()
    broker.deliver(QUEUE, b'{"session_id": "s1", "player_ids": ["ann", "bob"]}')
    settled(broker)

    assert broker.exchanges == {"games": ("topic", True)}
    assert broker.queues == {QUEUE: {}}
    assert broker.bindings == {(QUEUE, "games", "game.tictactoe.started")}
    assert [channel.prefetch for channel in consuming_channels(broker)] == [1]


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
    patient = ListenerTiming(retry_pause_seconds=30, max_retry_pause_seconds=30, poll_seconds=0.01, shutdown_seconds=2)
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


def test_the_pause_between_two_attempts_grows_by_the_multiplier_up_to_the_longest() -> None:
    timing = ListenerTiming(retry_pause_seconds=1, retry_multiplier=2, max_retry_pause_seconds=5)

    assert list(islice(timing.retry_pauses(), 5)) == [1, 2, 4, 5, 5]


def test_without_a_timing_a_message_is_tried_three_times_a_second_apart() -> None:
    timing = ListenerTiming()

    assert (timing.attempts, list(islice(timing.retry_pauses(), 2))) == (3, [1, 1])


def test_a_failing_message_is_tried_as_often_as_the_timing_says_while_the_connection_sleeps_between_attempts(
    broker: FakeBroker, listener: GameStartedListener, decorator: CountingTaskDecorator
) -> None:
    backing_off = ListenerTiming(
        attempts=4, retry_pause_seconds=0.1, retry_multiplier=2, max_retry_pause_seconds=0.25, poll_seconds=1
    )
    containers = RabbitListenerContainers(
        ScannedComponents(WORKING, listener),
        decorator,
        connection_factory_of(broker),
        auto_startup=True,
        timing=backing_off,
    )
    containers.start()
    try:
        broker.deliver(QUEUE, b'{"session_id": "crash", "player_ids": []}')
        settled(broker)
    finally:
        containers.stop()

    assert listener.attempts["crash"] == 4
    assert broker.rejected == [(1, False)]
    assert len(broker.slept) == 3  # one sleep per pause of 0.1, 0.2 and 0.25 s, each shorter than a poll
    assert sum(broker.slept) == pytest.approx(0.55, abs=0.05)


@pytest.fixture
def dead_letter_listener() -> GameFinishedListener:
    return GameFinishedListener()


@pytest.fixture
def dead_letter_containers(
    broker: FakeBroker, dead_letter_listener: GameFinishedListener, decorator: CountingTaskDecorator
) -> Iterator[RabbitListenerContainers]:
    components = ScannedComponents(DEAD_LETTER, dead_letter_listener)
    containers = RabbitListenerContainers(
        components, decorator, connection_factory_of(broker), auto_startup=True, timing=QUICK
    )
    yield containers
    containers.stop()


def test_a_listener_with_a_dead_letter_queue_declares_it_and_names_it_in_the_arguments_of_its_queue(
    dead_letter_containers: RabbitListenerContainers, broker: FakeBroker
) -> None:
    dead_letter_containers.start()

    assert broker.queues == {
        FINISHED_QUEUE: {"x-dead-letter-exchange": "", "x-dead-letter-routing-key": DEAD_LETTER_QUEUE},
        DEAD_LETTER_QUEUE: {},
    }
    assert broker.bindings == {(FINISHED_QUEUE, "games", "game.*.finished")}


@pytest.mark.parametrize(
    ("session_id", "attempts"),
    [("refuse", 1), ("crash", 3)],
    ids=["refused by the listener, without a retry", "failing on every attempt"],
)
def test_a_message_refused_for_good_is_rejected_without_requeue_for_rabbitmq_to_dead_letter_it(
    dead_letter_containers: RabbitListenerContainers,
    broker: FakeBroker,
    dead_letter_listener: GameFinishedListener,
    session_id: str,
    attempts: int,
) -> None:
    dead_letter_containers.start()
    broker.deliver(FINISHED_QUEUE, f'{{"session_id": "{session_id}"}}'.encode())
    settled(broker)

    assert dead_letter_listener.attempts[session_id] == attempts
    assert broker.rejected == [(1, False)]


def test_a_queue_that_exists_without_its_dead_letter_queue_stops_the_start_up_and_says_how_to_migrate(
    dead_letter_containers: RabbitListenerContainers, broker: FakeBroker
) -> None:
    broker.queues[FINISHED_QUEUE] = {}

    with pytest.raises(AmqpDeclarationError) as refused:
        dead_letter_containers.start()

    message = str(refused.value)
    assert "PRECONDITION_FAILED" in message
    assert f"rabbitmqctl delete_queue {FINISHED_QUEUE} --if-empty" in message
    assert f"rabbitmqctl set_policy {DEAD_LETTER_QUEUE} '^platform\\.game\\-finished$'" in message
    assert f'"dead-letter-routing-key": "{DEAD_LETTER_QUEUE}"' in message
    assert dead_letter_containers.running == 0


def test_a_queue_that_would_lose_its_dead_letter_queue_stops_the_start_up(
    containers: RabbitListenerContainers, broker: FakeBroker
) -> None:
    broker.queues[QUEUE] = {"x-dead-letter-exchange": "", "x-dead-letter-routing-key": f"{QUEUE}.dead-letter"}

    with pytest.raises(AmqpDeclarationError, match="give the listener dead_letter=True again"):
        containers.start()


def test_a_declaration_refused_after_the_start_up_is_tried_again_until_the_queue_is_migrated(
    dead_letter_containers: RabbitListenerContainers,
    broker: FakeBroker,
    dead_letter_listener: GameFinishedListener,
    caplog: pytest.LogCaptureFixture,
) -> None:
    broker.unreachable_attempts = 1  # down while the application starts, so the start-up cannot check
    broker.queues[FINISHED_QUEUE] = {}
    dead_letter_containers.start()
    deadline = time.monotonic() + WAIT_SECONDS
    while not any(record.levelname == "ERROR" and "delete_queue" in record.getMessage() for record in caplog.records):
        assert time.monotonic() < deadline, "the refused declaration was not logged"
        time.sleep(0.01)

    del broker.queues[FINISHED_QUEUE]  # what `rabbitmqctl delete_queue` does
    broker.deliver(FINISHED_QUEUE, b'{"session_id": "s1"}')
    settled(broker)

    assert dead_letter_listener.finished == ["s1"]


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

    with pytest.raises(InvalidRabbitListenerError, match="GameStartedListener is no component: add @component"):
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
