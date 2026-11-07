"""Registers the connection factory, the RabbitTemplate and the listener containers with wireup.

`snakeboot.django_application` adds this module to the container only when the application has a `[rabbitmq]`
section, like Spring Boot's `RabbitAutoConfiguration` with its conditions: an application without the section needs
neither pika nor a broker.
"""

from wireup import injectable

from snakeboot.configuration.rabbitmq_properties import RabbitProperties
from snakeboot.lifecycle.application_components import ApplicationComponents
from snakeboot.lifecycle.lifecycle import Lifecycle
from snakeboot.lifecycle.task_decorator import TaskDecorator
from snakeboot.rabbitmq.rabbit_connection_factory import RabbitConnectionFactory
from snakeboot.rabbitmq.rabbit_listener_containers import RabbitListenerContainers
from snakeboot.rabbitmq.rabbit_template import RabbitTemplate


@injectable
def rabbit_connection_factory(properties: RabbitProperties) -> RabbitConnectionFactory:
    """Provides the factory of every connection to the broker of `[rabbitmq]`."""
    return RabbitConnectionFactory(properties)


@injectable
def rabbit_template(connection_factory: RabbitConnectionFactory) -> RabbitTemplate:
    """Provides the one RabbitTemplate, which adapters inject to send messages."""
    return RabbitTemplate(connection_factory)


@injectable(as_type=Lifecycle, qualifier="snakeboot.rabbitmq.RabbitListenerContainers")
def rabbit_listener_containers(
    components: ApplicationComponents,
    task_decorator: TaskDecorator,
    connection_factory: RabbitConnectionFactory,
    *,
    properties: RabbitProperties,
) -> RabbitListenerContainers:
    """Provides the listener containers; `[rabbitmq.listener] auto_startup = false` keeps them from consuming."""
    return RabbitListenerContainers(
        components, task_decorator, connection_factory, auto_startup=properties.listener.auto_startup
    )
