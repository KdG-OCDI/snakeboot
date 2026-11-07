"""The RabbitTemplate sends persistent JSON messages, confirmed by the broker, and tries a fresh connection once."""

import json
import threading
from datetime import UTC, datetime

import pika
import pytest
from pydantic import BaseModel

from snakeboot.rabbitmq import AmqpPublishError, RabbitTemplate
from tests.rabbitmq.fake_broker import FakeBroker
from tests.rabbitmq.stand_ins import connection_factory_of


class GameFinished(BaseModel):
    """Stands in for an event a game publishes."""

    session_id: str
    winner_id: str | None
    occurred_at: datetime


FINISHED = GameFinished(session_id="s1", winner_id="ann", occurred_at=datetime(2026, 11, 7, 12, tzinfo=UTC))


@pytest.fixture
def broker() -> FakeBroker:
    return FakeBroker()


@pytest.fixture
def template(broker: FakeBroker) -> RabbitTemplate:
    return RabbitTemplate(connection_factory_of(broker))


def test_sends_the_payload_as_a_persistent_json_message(template: RabbitTemplate, broker: FakeBroker) -> None:
    template.convert_and_send("games", "game.tictactoe.finished", FINISHED, message_id="s1.finished")

    [message] = broker.published
    assert (message.exchange, message.routing_key) == ("games", "game.tictactoe.finished")
    assert json.loads(message.body) == {"session_id": "s1", "winner_id": "ann", "occurred_at": "2026-11-07T12:00:00Z"}
    assert message.properties.content_type == "application/json"
    assert message.properties.delivery_mode == pika.DeliveryMode.Persistent.value
    assert message.properties.message_id == "s1.finished"


def test_waits_for_the_broker_to_confirm_and_declares_the_exchange_once(
    template: RabbitTemplate, broker: FakeBroker
) -> None:
    template.convert_and_send("games", "a", {"n": 1})
    template.convert_and_send("games", "b", {"n": 2})

    [connection] = broker.connections
    assert connection.channels[0].confirms
    assert broker.exchanges == {"games": ("topic", True)}
    assert len(broker.published) == 2


def test_a_lost_connection_is_replaced_and_the_message_sent_once_more(
    template: RabbitTemplate, broker: FakeBroker
) -> None:
    template.convert_and_send("games", "a", {"n": 1})
    broker.lost_publishes = 1

    template.convert_and_send("games", "b", {"n": 2})

    assert [message.routing_key for message in broker.published] == ["a", "b"]
    assert len(broker.connections) == 2


def test_a_message_that_does_not_arrive_on_a_fresh_connection_either_is_an_error(
    template: RabbitTemplate, broker: FakeBroker
) -> None:
    broker.lost_publishes = 2

    with pytest.raises(AmqpPublishError, match="did not take a message to games/a"):
        template.convert_and_send("games", "a", {"n": 1})


def test_a_broker_that_is_down_is_an_error_too(template: RabbitTemplate, broker: FakeBroker) -> None:
    broker.unreachable_attempts = 2

    with pytest.raises(AmqpPublishError):
        template.convert_and_send("games", "a", {"n": 1})


def test_every_thread_sends_over_a_connection_of_its_own(template: RabbitTemplate, broker: FakeBroker) -> None:
    template.convert_and_send("games", "main", {"n": 1})
    other = threading.Thread(target=template.convert_and_send, args=("games", "other", {"n": 2}))
    other.start()
    other.join()

    assert len(broker.connections) == 2
