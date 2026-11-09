import contextlib
import threading
import time
from dataclasses import dataclass
from typing import Any

import pika
from pika.exceptions import AMQPError

from snakeboot.rabbitmq.message_conversion import body_of
from snakeboot.rabbitmq.rabbit_connection_factory import RabbitConnectionFactory
from snakeboot.tracing import TRACEPARENT, TraceContext


class AmqpPublishError(RuntimeError):
    """RabbitMQ did not take a message, even on a fresh connection; like Spring AMQP's `AmqpException`."""


class RabbitTemplate:
    """Sends messages to RabbitMQ, like Spring AMQP's `RabbitTemplate`.

        self._rabbit.convert_and_send("games", "game.tictactoe.finished", event, message_id=f"{game_id}.finished")

    The payload becomes a persistent JSON message, with the `traceparent` of the work in hand, so the listener
    continues its trace. `convert_and_send` returns once the broker confirmed it (publisher confirms); a connection
    that went stale is replaced and the message sent once more, then `AmqpPublishError` says it did not arrive. Each
    thread uses a connection of its own, as pika requires. The topic exchange is declared (durable) before the first
    message to it, so sending works before anyone listens.
    """

    def __init__(self, connection_factory: RabbitConnectionFactory) -> None:
        self._connection_factory = connection_factory
        self._local = threading.local()

    def convert_and_send(
        self, exchange: str, routing_key: str, payload: object, *, message_id: str | None = None
    ) -> None:
        """Sends `payload` as JSON to `exchange` with `routing_key`; raises AmqpPublishError when it did not arrive."""
        body = body_of(payload)
        span = TraceContext.current()
        properties = pika.BasicProperties(
            content_type="application/json",
            delivery_mode=pika.DeliveryMode.Persistent,
            message_id=message_id,
            timestamp=int(time.time()),
            headers={TRACEPARENT: span.traceparent} if span is not None else None,
        )
        message = _OutgoingMessage(exchange, routing_key, body, properties)
        try:
            self._publish(message)
        except AMQPError:
            self._forget_connection()
            try:
                self._publish(message)
            except AMQPError as error:
                self._forget_connection()
                raise AmqpPublishError(
                    f"RabbitMQ did not take a message to {exchange}/{routing_key}: {error!r}"
                ) from error

    def _publish(self, message: "_OutgoingMessage") -> None:
        channel = self._channel()
        declared: set[str] = self._local.declared
        if message.exchange and message.exchange not in declared:
            channel.exchange_declare(exchange=message.exchange, exchange_type="topic", durable=True)
            declared.add(message.exchange)
        channel.basic_publish(
            exchange=message.exchange, routing_key=message.routing_key, body=message.body, properties=message.properties
        )

    def _channel(self) -> Any:
        channel = getattr(self._local, "channel", None)
        if channel is None or not channel.is_open:
            self._forget_connection()
            connection = self._connection_factory.open()
            channel = connection.channel()
            channel.confirm_delivery()
            self._local.connection = connection
            self._local.channel = channel
            self._local.declared = set()
        return channel

    def _forget_connection(self) -> None:
        connection = getattr(self._local, "connection", None)
        self._local.connection = None
        self._local.channel = None
        if connection is not None and connection.is_open:
            with contextlib.suppress(AMQPError):  # it is broken already; a new one replaces it
                connection.close()


@dataclass(frozen=True, slots=True)
class _OutgoingMessage:
    exchange: str
    routing_key: str
    body: bytes
    properties: Any
