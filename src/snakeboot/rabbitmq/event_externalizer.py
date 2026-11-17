from collections.abc import Iterable

from snakeboot.events import (
    EventPublicationRegistry,
    ExternalizedEvent,
    InvalidApplicationEventListenerError,
    InvalidExternalizationError,
    application_module_listener,
    externalization_target,
)
from snakeboot.rabbitmq.rabbit_template import RabbitTemplate


class EventExternalizer:
    """Sends every event of an `@externalized` class to RabbitMQ, like Spring Modulith's externalization for AMQP.

    It is an `@application_module_listener` of `ExternalizedEvent`: once the publisher's transaction committed, it
    sends the event, on a thread and in a transaction of its own, to the exchange of its `@externalized` target with
    its key as the routing key. With a database the publication waits in the event publication registry until the
    broker confirmed the message, so the event reaches RabbitMQ at least once, also after the broker or the process
    was down. Outside a transaction it sends the event at once (`fallback_execution`), kept in no registry.

    `snakeboot.rabbitmq.rabbitmq_injectable` registers it as a listener when the application has `[rabbitmq]`.
    """

    def __init__(self, rabbit: RabbitTemplate) -> None:
        self._rabbit = rabbit

    @staticmethod
    def verify(event_types: Iterable[type], registries: Iterable[EventPublicationRegistry]) -> None:
        """Stops the start-up when a registry cannot keep the events of one of the `@externalized` `event_types`."""
        types = list(event_types)
        for registry in registries:
            try:
                registry.verify(types)
            except InvalidApplicationEventListenerError as error:
                raise InvalidExternalizationError(
                    f"An @externalized event must be kept as JSON until it was sent: {error}"
                ) from error

    @application_module_listener(ExternalizedEvent, fallback_execution=True)
    def externalize(self, event: ExternalizedEvent) -> None:
        """Sends `event` to its target; raises AmqpPublishError, so it is sent again later, when it did not arrive."""
        destination = externalization_target(event)
        self._rabbit.convert_and_send(destination.target, destination.key, event)
