"""On RabbitMQ: a message refused for good ends in the dead-letter queue, a queue that exists keeps its arguments, and
a long pause between two attempts keeps the connection.

Set SNAKEBOOT_TEST_RABBITMQ_URL to a broker on which these tests may declare and delete the queues of the sample
listeners and the exchange `games`, such as `docker run -p 55672:5672 rabbitmq:4-management`:

    SNAKEBOOT_TEST_RABBITMQ_URL=amqp://guest:guest@localhost:55672/%2F
"""

import json
import os
import time
from collections.abc import Iterator
from typing import Any

import pika
import pytest

from snakeboot.rabbitmq import AmqpDeclarationError, ListenerTiming, RabbitConnectionFactory, RabbitListenerContainers
from tests.rabbitmq.sample_listeners.dead_letter.listeners import GameFinishedListener
from tests.rabbitmq.sample_listeners.working.listeners import GameStartedListener
from tests.rabbitmq.stand_ins import rabbit_properties
from tests.scheduling.stand_ins import CountingTaskDecorator, ScannedComponents

URL = os.environ.get("SNAKEBOOT_TEST_RABBITMQ_URL", "")

pytestmark = pytest.mark.skipif(not URL, reason="SNAKEBOOT_TEST_RABBITMQ_URL names no RabbitMQ")

WORKING = "tests.rabbitmq.sample_listeners.working"
DEAD_LETTER = "tests.rabbitmq.sample_listeners.dead_letter"
STARTED_QUEUE = "tictactoe.game-started"
FINISHED_QUEUE = "platform.game-finished"
DEAD_LETTER_QUEUE = "platform.game-finished.dead-letter"
QUICK = ListenerTiming(reconnect_seconds=0.1, retry_pause_seconds=0, poll_seconds=0.05, shutdown_seconds=5)
WAIT_SECONDS = 10


def connection_factory(*, heartbeat: int | None = None) -> RabbitConnectionFactory:
    parameters = pika.URLParameters(URL)
    if heartbeat is not None:
        parameters.heartbeat = heartbeat
    return RabbitConnectionFactory(rabbit_properties(), connect=lambda _: pika.BlockingConnection(parameters))


def forget_the_sample_listeners(channel: Any) -> None:
    for queue in (STARTED_QUEUE, FINISHED_QUEUE, DEAD_LETTER_QUEUE):
        channel.queue_delete(queue)
    channel.exchange_delete("games")


@pytest.fixture
def channel() -> Iterator[Any]:
    connection = pika.BlockingConnection(pika.URLParameters(URL))
    channel = connection.channel()
    forget_the_sample_listeners(channel)
    yield channel
    forget_the_sample_listeners(channel)
    connection.close()


def next_message(channel: Any, queue: str) -> tuple[Any, bytes]:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        method, properties, body = channel.basic_get(queue, auto_ack=True)
        if method is not None:
            return properties, body
        channel.connection.sleep(0.05)
    pytest.fail(f"no message arrived in {queue}")


def dead_letter_containers(listener: GameFinishedListener) -> RabbitListenerContainers:
    components = ScannedComponents(DEAD_LETTER, listener)
    return RabbitListenerContainers(
        components, CountingTaskDecorator(), connection_factory(), auto_startup=True, timing=QUICK
    )


@pytest.mark.parametrize(
    ("session_id", "attempts"),
    [("refuse", 1), ("crash", 3)],
    ids=["refused by the listener, without a retry", "failing on every attempt"],
)
def test_a_message_refused_for_good_ends_in_the_dead_letter_queue(channel: Any, session_id: str, attempts: int) -> None:
    listener = GameFinishedListener()
    containers = dead_letter_containers(listener)
    containers.start()
    try:
        channel.basic_publish("games", "game.tictactoe.finished", json.dumps({"session_id": session_id}).encode())
        properties, body = next_message(channel, DEAD_LETTER_QUEUE)
    finally:
        containers.stop()

    assert json.loads(body) == {"session_id": session_id}
    assert (properties.headers["x-first-death-queue"], properties.headers["x-first-death-reason"]) == (
        FINISHED_QUEUE,
        "rejected",
    )
    assert listener.attempts[session_id] == attempts


def test_a_queue_that_exists_without_its_dead_letter_queue_stops_the_start_up_until_it_is_deleted(
    channel: Any,
) -> None:
    channel.queue_declare(FINISHED_QUEUE, durable=True)
    containers = dead_letter_containers(GameFinishedListener())

    with pytest.raises(AmqpDeclarationError, match=r"inequivalent arg 'x-dead-letter-exchange'.*delete_queue"):
        containers.start()

    channel.queue_delete(FINISHED_QUEUE, if_empty=True)  # the migration the message names
    containers.start()
    containers.stop()


def test_a_long_pause_between_two_attempts_keeps_the_connection(channel: Any) -> None:
    listener = GameStartedListener()
    patient = ListenerTiming(
        reconnect_seconds=0.1,
        attempts=2,
        retry_pause_seconds=5,
        max_retry_pause_seconds=5,
        poll_seconds=0.5,
        shutdown_seconds=5,
    )
    components = ScannedComponents(WORKING, listener)
    # A heartbeat of a second: the broker closes a connection that stays silent for a few seconds.
    containers = RabbitListenerContainers(
        components, CountingTaskDecorator(), connection_factory(heartbeat=1), auto_startup=True, timing=patient
    )
    containers.start()
    try:
        channel.basic_publish("games", "game.tictactoe.started", b'{"session_id": "flaky", "player_ids": []}')
        assert listener.received.wait(WAIT_SECONDS)
    finally:
        containers.stop()

    left = channel.queue_declare(STARTED_QUEUE, durable=True, passive=True).method.message_count
    assert (listener.attempts["flaky"], len(listener.started), left) == (2, 1, 0)
