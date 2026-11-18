import uuid
from collections.abc import Sequence
from typing import Self

from snakeboot.events import (
    EventExternalization,
    application_module_listener,
    externalization_target,
    publication_in_hand,
)
from snakeboot.rabbitmq.rabbit_template import RabbitTemplate


class EventExternalizer(EventExternalization):
    """Sends every event of an `@externalized` class to RabbitMQ, like Spring Modulith's externalization for AMQP.

    Its method `externalize` is an `@application_module_listener` of the `@externalized` classes of the component
    scan: once the publisher's transaction committed, it sends the event, on a thread and in a transaction of its own,
    to the exchange of its target with its key as the routing key. With a database the publication waits in the event
    publication registry until the broker confirmed the message, so the event reaches RabbitMQ at least once, also
    after the broker or the process was down; the message id is the publication's, the same each time it is sent
    again. Outside a transaction it sends the event at once (`fallback_execution`), kept in no registry, with a new
    message id. An application without `@externalized` events gets an externalizer that hears none, and so starts no
    resubmission of the registry for it.

    `snakeboot.rabbitmq.rabbitmq_injectable` registers it as a listener when the application has `[rabbitmq]`.
    """

    def __init__(self, rabbit: RabbitTemplate) -> None:
        self._rabbit = rabbit

    @classmethod
    def listening_to(cls, event_types: Sequence[type], rabbit: RabbitTemplate) -> Self:
        """Returns an externalizer whose listener method hears `event_types`, and their subclasses.

        The event types are the application's, so the listener method is made for them: a class of its own with the
        same name, so the registry knows its publications by the same listener name in every application.
        """

        def externalize(self: EventExternalizer, event: object) -> None:
            self.send(event)

        listener = application_module_listener(*event_types, fallback_execution=True)(externalize)
        members = {"__module__": cls.__module__, "__qualname__": cls.__qualname__, "externalize": listener}
        externalizer_class: type[Self] = type(cls.__name__, (cls,), members)
        return externalizer_class(rabbit)

    def send(self, event: object) -> None:
        """Sends `event` to its target; raises AmqpPublishError, so it is sent again later, when it did not arrive."""
        destination = externalization_target(event)
        publication = publication_in_hand()
        message_id = str(publication.identifier if publication is not None else uuid.uuid4())
        self._rabbit.convert_and_send(destination.target, destination.key, event, message_id=message_id)
