"""The application and the broker, as the RabbitMQ tests give them."""

from pydantic import SecretStr

from snakeboot.configuration import RabbitListenerProperties, RabbitProperties
from snakeboot.rabbitmq import RabbitConnectionFactory
from tests.rabbitmq.fake_broker import FakeBroker


def rabbit_properties(*, auto_startup: bool = True) -> RabbitProperties:
    """A `[rabbitmq]` section, as application.toml would hold it."""
    return RabbitProperties(
        host="rabbitmq",
        port=5672,
        username="guest",
        password=SecretStr("guest"),
        virtual_host="/",
        listener=RabbitListenerProperties(auto_startup=auto_startup),
    )


def connection_factory_of(broker: FakeBroker) -> RabbitConnectionFactory:
    """Connections to the stand-in broker instead of a real one."""
    return RabbitConnectionFactory(rabbit_properties(), connect=broker.connect)
