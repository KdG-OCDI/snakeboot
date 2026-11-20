"""A listener may bind its queue or stream with several routing keys, as `@QueueBinding(key = {...})` does."""

import time
from collections.abc import Callable, Iterator
from typing import override

import pytest

from snakeboot.events import InMemoryStreamOffsets
from snakeboot.lifecycle import TaskDecorator
from snakeboot.rabbitmq import (
    InProcessRabbitTemplate,
    InvalidRabbitListenerError,
    ListenerTiming,
    RabbitListenerContainers,
    RabbitListenerMapping,
    RabbitStreamListenerContainers,
    rabbit_listener,
    rabbit_stream_listener,
)
from snakeboot.rabbitmq.rabbit_listener import RABBIT_LISTENER_MAPPING_ATTRIBUTE
from snakeboot.rabbitmq.rabbit_stream_listener_containers import rabbit_stream_listener_endpoints
from tests.rabbitmq.fake_broker import FakeBroker
from tests.rabbitmq.sample_listeners.several_keys.listeners import GameLifecycleListener, GameResultProjection
from tests.rabbitmq.stand_ins import connection_factory_of
from tests.scheduling.stand_ins import CountingTaskDecorator, ScannedComponents

PACKAGE = "tests.rabbitmq.sample_listeners.several_keys"
QUEUE = "arena.game-lifecycle"
STREAM = "games.history"
QUICK = ListenerTiming(
    reconnect_seconds=0.01, retry_pause_seconds=0, poll_seconds=0.01, shutdown_seconds=2, stream_check_seconds=0.05
)
WAIT_SECONDS = 5


class SampleComponents(ScannedComponents):
    """The sample package's listeners, and the task decorator the in-process template asks for."""

    def __init__(self, *components: object) -> None:
        super().__init__(PACKAGE, *components)
        self._decorator = CountingTaskDecorator()

    @override
    def get[T](self, component_type: Callable[..., T]) -> T:
        if component_type is TaskDecorator:
            decorator: T = self._decorator  # type: ignore[assignment]  # reason: the decorator is a TaskDecorator
            return decorator
        return super().get(component_type)


@pytest.fixture
def broker() -> FakeBroker:
    return FakeBroker()


@pytest.fixture
def listener() -> GameLifecycleListener:
    return GameLifecycleListener()


@pytest.fixture
def projection() -> GameResultProjection:
    return GameResultProjection()


@pytest.fixture
def queue_containers(broker: FakeBroker, listener: GameLifecycleListener) -> Iterator[RabbitListenerContainers]:
    containers = RabbitListenerContainers(
        ScannedComponents(PACKAGE, listener),
        CountingTaskDecorator(),
        connection_factory_of(broker),
        auto_startup=True,
        timing=QUICK,
    )
    yield containers
    containers.stop()


@pytest.fixture
def stream_containers(broker: FakeBroker, projection: GameResultProjection) -> Iterator[RabbitStreamListenerContainers]:
    components = ScannedComponents(PACKAGE, projection)
    containers = RabbitStreamListenerContainers(
        lambda: rabbit_stream_listener_endpoints(components, CountingTaskDecorator(), InMemoryStreamOffsets()),
        connection_factory_of(broker),
        auto_startup=True,
        timing=QUICK,
    )
    yield containers
    containers.stop()


def game(session_id: str, what: str) -> bytes:
    return f'{{"session_id": "{session_id}", "what": "{what}"}}'.encode()


def eventually(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    while not condition():
        assert time.monotonic() < deadline, "the condition never held"
        time.sleep(0.01)


def lifecycle_mapping() -> RabbitListenerMapping:
    mapping = getattr(GameLifecycleListener.on_game_event, RABBIT_LISTENER_MAPPING_ATTRIBUTE)
    assert isinstance(mapping, RabbitListenerMapping)
    return mapping


def test_the_mapping_keeps_every_routing_key_and_matches_what_any_of_them_matches() -> None:
    mapping = lifecycle_mapping()

    assert mapping.routing_keys == ("game.*.started", "game.*.finished")
    assert [mapping.matches(key) for key in ("game.chess.started", "game.chess.finished", "game.chess.paused")] == [
        True,
        True,
        False,
    ]


def test_one_routing_key_is_a_tuple_of_one() -> None:
    @rabbit_listener(queue="q", exchange="e", routing_key="a.b")
    def on_message(message: bytes) -> None: ...

    mapping = getattr(on_message, RABBIT_LISTENER_MAPPING_ATTRIBUTE)
    assert mapping.routing_keys == ("a.b",)


def test_the_queue_is_bound_once_for_each_routing_key(
    queue_containers: RabbitListenerContainers, broker: FakeBroker, listener: GameLifecycleListener
) -> None:
    queue_containers.start()
    broker.deliver(QUEUE, game("g1", "started"), routing_key="game.chess.started")
    assert broker.settled.wait(WAIT_SECONDS)

    assert broker.bindings == {(QUEUE, "games", "game.*.started"), (QUEUE, "games", "game.*.finished")}
    assert [event.session_id for event in listener.received] == ["g1"]


def test_the_stream_is_bound_once_for_each_routing_key_and_its_method_handles_what_any_matches(
    stream_containers: RabbitStreamListenerContainers, broker: FakeBroker, projection: GameResultProjection
) -> None:
    broker.append(STREAM, game("g1", "started"), routing_key="game.chess.started")
    broker.append(STREAM, game("g1", "finished"), routing_key="game.chess.finished")
    broker.append(STREAM, game("g2", "abandoned"), routing_key="game.go.abandoned")

    stream_containers.start()
    eventually(lambda: len(broker.acked) == 3)

    assert broker.bindings == {(STREAM, "games", "game.*.finished"), (STREAM, "games", "game.*.abandoned")}
    assert [(result.session_id, result.what) for result in projection.results] == [
        ("g1", "finished"),
        ("g2", "abandoned"),
    ]


def test_the_in_process_template_routes_by_any_routing_key_of_a_listener(
    listener: GameLifecycleListener, projection: GameResultProjection
) -> None:
    rabbit = InProcessRabbitTemplate(SampleComponents(listener, projection))

    for routing_key, what in [("game.chess.started", "started"), ("game.chess.paused", "paused")]:
        rabbit.convert_and_send("games", routing_key, {"session_id": "g1", "what": what})
    rabbit.convert_and_send("games", "game.chess.finished", {"session_id": "g1", "what": "finished"})

    assert [event.what for event in listener.received] == ["started", "finished"]
    assert [result.what for result in projection.results] == ["finished"]
    assert rabbit.refused == []


@pytest.mark.parametrize(
    "declare",
    [
        lambda: rabbit_listener(queue="nowhere", exchange="games", routing_key=()),
        lambda: rabbit_stream_listener(stream="nowhere", exchange="games", routing_key=[]),
    ],
    ids=["queue", "stream"],
)
def test_a_listener_without_a_routing_key_stops_the_start(declare: Callable[[], object]) -> None:
    with pytest.raises(InvalidRabbitListenerError, match=r"'nowhere'.*names no routing key"):
        declare()
