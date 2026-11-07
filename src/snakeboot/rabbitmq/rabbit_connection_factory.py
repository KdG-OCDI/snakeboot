from collections.abc import Callable
from typing import Any

import pika

from snakeboot.configuration.rabbitmq_properties import RabbitProperties


class RabbitConnectionFactory:
    """Opens connections to the broker of `[rabbitmq]`, like Spring AMQP's `ConnectionFactory`.

    Every listener and every thread that sends gets a connection of its own: pika's `BlockingConnection` may only be
    used by the thread that opened it. `connect` opens one; tests give a stand-in for the broker.
    """

    def __init__(
        self,
        properties: RabbitProperties,
        connect: Callable[[pika.ConnectionParameters], Any] = pika.BlockingConnection,
    ) -> None:
        self._parameters = pika.ConnectionParameters(
            host=properties.host,
            port=properties.port,
            virtual_host=properties.virtual_host,
            credentials=pika.PlainCredentials(properties.username, properties.password.get_secret_value()),
            connection_attempts=1,
        )
        self._connect = connect

    @property
    def parameters(self) -> pika.ConnectionParameters:
        """Where and as whom the connections log in."""
        return self._parameters

    def open(self) -> Any:
        """Opens a `BlockingConnection`; raises pika's `AMQPConnectionError` when the broker cannot be reached."""
        return self._connect(self._parameters)
