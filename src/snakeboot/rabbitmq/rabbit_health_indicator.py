from typing import override

from snakeboot.actuator import HealthIndicator
from snakeboot.rabbitmq.rabbit_connection_factory import RabbitConnectionFactory


class RabbitHealthIndicator(HealthIndicator, component=False):
    """Checks that the broker answers, like Spring Boot's `RabbitHealthIndicator`: it opens a connection and closes it.

    A connection of its own: pika's connections belong to the thread that opened them, and a check runs on any.
    """

    def __init__(self, connection_factory: RabbitConnectionFactory) -> None:
        self._connection_factory = connection_factory

    @override
    def check(self) -> None:
        self._connection_factory.open().close()
