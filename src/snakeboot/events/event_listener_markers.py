from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

LISTENER_MAPPING_ATTRIBUTE: Final = "__application_event_listener_mapping__"

APPLICATION_MODULE_LISTENER_ATTRIBUTE: Final = "__application_module_listener_mapping__"
"""The mark `@application_module_listener` leaves on its method besides the listener's: the mark of a method that needs
the table of the event publication registry."""

type MethodMarker = Callable[[Callable[..., Any]], Callable[..., Any]]


class Delivery(StrEnum):
    """When, and on which thread, a listener method receives an event."""

    IN_TRANSACTION = "in_transaction"
    """At once, on the publisher's thread, inside its transaction (`@event_listener`)."""
    AFTER_COMMIT = "after_commit"
    """Once the publisher's transaction committed, on its thread (`@transactional_event_listener`)."""
    ASYNC_AFTER_COMMIT = "async_after_commit"
    """Once the publisher's transaction committed, on a thread of its own, in a transaction of its own; kept in the
    event publication registry until it succeeds (`@application_module_listener`)."""


@dataclass(frozen=True, slots=True)
class ListenerMapping:
    """What a listener marker records on a method: the events it receives and when."""

    event_types: tuple[type, ...]
    delivery: Delivery


def event_listener(*event_types: type) -> MethodMarker:
    """Marks a method that receives `event_types` at once, inside the publisher's transaction (`@EventListener`).

    Use it for work that must commit or roll back together with the change that caused the event.
    """
    return _mark(event_types, Delivery.IN_TRANSACTION)


def transactional_event_listener(*event_types: type) -> MethodMarker:
    """Marks a method that receives `event_types` once the transaction has committed.

    Spring: `@TransactionalEventListener(phase = AFTER_COMMIT)`. Use it for effects outside the
    database, such as notifications: they are delivered through `after_commit`, so a rolled-back
    change never reaches anyone, and a failing listener cannot undo the committed change. A listener
    that fails, or a process that stops before it ran, loses the event: for what must arrive, use
    `@application_module_listener`.
    """
    return _mark(event_types, Delivery.AFTER_COMMIT)


def application_module_listener(*event_types: type) -> MethodMarker:
    """Marks a method that receives `event_types` after the commit, on a thread and in a transaction of its own.

    Spring Modulith's `@ApplicationModuleListener`: `@Async`, `@Transactional(propagation = REQUIRES_NEW)` and
    `@TransactionalEventListener` at once. One module reacts to the facts of another without slowing it down, and
    a failure of one cannot roll back the other. With a database, the publisher's transaction also writes the
    publication into the event publication registry (a transactional outbox): it is deleted in the listener's own
    transaction when the listener succeeds, and delivered again when the listener fails or the process stopped
    first. So the event arrives at least once, and the listener must bear receiving it twice.

        @application_event_listener
        class InvoiceOnOrderPlaced:
            @application_module_listener(OrderPlaced)
            def create_invoice(self, event: OrderPlaced) -> None: ...

    The event is kept as JSON: a dataclass or a Pydantic model whose fields JSON can hold.
    """
    return _mark(event_types, Delivery.ASYNC_AFTER_COMMIT)


def _mark(event_types: tuple[type, ...], delivery: Delivery) -> MethodMarker:
    def record(method: Callable[..., Any]) -> Callable[..., Any]:
        mapping = ListenerMapping(event_types, delivery)
        setattr(method, LISTENER_MAPPING_ATTRIBUTE, mapping)
        if delivery is Delivery.ASYNC_AFTER_COMMIT:
            setattr(method, APPLICATION_MODULE_LISTENER_ATTRIBUTE, mapping)
        return method

    return record
