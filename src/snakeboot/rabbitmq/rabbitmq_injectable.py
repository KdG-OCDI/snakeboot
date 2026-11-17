"""Registers the connection factory, the RabbitTemplate, the listener containers and the event externalizer with wireup.

`snakeboot.boot` adds this module to the container only when the application has a `[rabbitmq]`
section, like Spring Boot's `RabbitAutoConfiguration` with its conditions: an application without the section needs
neither pika nor a broker.
"""

from collections.abc import Sequence

from wireup import injectable

from snakeboot.actuator import HealthIndicator
from snakeboot.configuration.rabbitmq_properties import RabbitListenerRetryProperties, RabbitProperties
from snakeboot.events import ApplicationEventListener, EventPublicationRegistry
from snakeboot.events.externalized import EXTERNALIZED_ATTRIBUTE
from snakeboot.lifecycle.application_components import ApplicationComponents
from snakeboot.lifecycle.lifecycle import Lifecycle
from snakeboot.lifecycle.task_decorator import TaskDecorator
from snakeboot.rabbitmq.event_externalizer import EventExternalizer
from snakeboot.rabbitmq.rabbit_connection_factory import RabbitConnectionFactory
from snakeboot.rabbitmq.rabbit_health_indicator import RabbitHealthIndicator
from snakeboot.rabbitmq.rabbit_listener_containers import ListenerTiming, RabbitListenerContainers
from snakeboot.rabbitmq.rabbit_stream_listener_containers import (
    RabbitStreamListenerContainers,
    RabbitStreamListenerEndpoint,
    rabbit_stream_listener_endpoints,
    stream_offsets_of,
)
from snakeboot.rabbitmq.rabbit_template import RabbitTemplate


@injectable
def rabbit_connection_factory(properties: RabbitProperties) -> RabbitConnectionFactory:
    """Provides the factory of every connection to the broker of `[rabbitmq]`."""
    return RabbitConnectionFactory(properties)


@injectable
def rabbit_template(connection_factory: RabbitConnectionFactory) -> RabbitTemplate:
    """Provides the one RabbitTemplate, which adapters inject to send messages."""
    return RabbitTemplate(connection_factory)


@injectable(as_type=HealthIndicator, qualifier="snakeboot.rabbitmq.RabbitHealthIndicator")
def rabbit_health_indicator(connection_factory: RabbitConnectionFactory) -> HealthIndicator:
    """Provides the check of the broker that `/health` runs."""
    return RabbitHealthIndicator(connection_factory)


@injectable(as_type=Lifecycle, qualifier="snakeboot.rabbitmq.RabbitListenerContainers")
def rabbit_listener_containers(
    components: ApplicationComponents,
    task_decorator: TaskDecorator,
    connection_factory: RabbitConnectionFactory,
    *,
    properties: RabbitProperties,
) -> RabbitListenerContainers:
    """Provides the listener containers; `[rabbitmq.listener] auto_startup = false` keeps them from consuming, and
    `[rabbitmq.listener.retry]` says how often and how patiently a failing message is tried."""
    return RabbitListenerContainers(
        components,
        task_decorator,
        connection_factory,
        auto_startup=properties.listener.auto_startup,
        timing=listener_timing(properties.listener.retry),
    )


@injectable(as_type=Lifecycle, qualifier="snakeboot.rabbitmq.RabbitStreamListenerContainers")
def rabbit_stream_listener_containers(
    components: ApplicationComponents,
    task_decorator: TaskDecorator,
    connection_factory: RabbitConnectionFactory,
    *,
    properties: RabbitProperties,
) -> RabbitStreamListenerContainers:
    """Provides the containers of the stream listeners; `[rabbitmq.listener]` applies to them as to the others."""

    def endpoints() -> list[RabbitStreamListenerEndpoint]:
        return rabbit_stream_listener_endpoints(components, task_decorator, stream_offsets_of(components))

    return RabbitStreamListenerContainers(
        endpoints,
        connection_factory,
        auto_startup=properties.listener.auto_startup,
        timing=listener_timing(properties.listener.retry),
    )


@injectable(as_type=ApplicationEventListener, qualifier="snakeboot.rabbitmq.EventExternalizer")
def event_externalizer(
    rabbit: RabbitTemplate, components: ApplicationComponents, registries: Sequence[EventPublicationRegistry] = ()
) -> ApplicationEventListener:
    """Provides the listener that sends every `@externalized` event to RabbitMQ; an event the registry cannot keep
    stops the start."""
    EventExternalizer.verify(components.classes_marked(EXTERNALIZED_ATTRIBUTE), registries)
    return EventExternalizer(rabbit)


def listener_timing(retry: RabbitListenerRetryProperties | None) -> ListenerTiming:
    """Returns the timing of the listeners with the retry of `[rabbitmq.listener.retry]`, or snakeboot's own retry
    (three attempts, a second apart) without that table."""
    if retry is None:
        return ListenerTiming()
    return ListenerTiming(
        attempts=retry.max_attempts,
        retry_pause_seconds=retry.initial_interval.total_seconds(),
        retry_multiplier=retry.multiplier,
        max_retry_pause_seconds=retry.max_interval.total_seconds(),
    )
