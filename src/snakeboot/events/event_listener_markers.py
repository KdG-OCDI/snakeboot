from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from snakeboot.transaction import TransactionPhase

LISTENER_MAPPING_ATTRIBUTE: Final = "__application_event_listener_mapping__"

APPLICATION_MODULE_LISTENER_ATTRIBUTE: Final = "__application_module_listener_mapping__"
"""The mark `@application_module_listener` leaves on its method besides the listener's: the mark of a method that needs
the table of the event publication registry."""

type MethodMarker = Callable[[Callable[..., Any]], Callable[..., Any]]


class Delivery(StrEnum):
    """When, and on which thread, a listener method receives an event."""

    IN_TRANSACTION = "in_transaction"
    """At once, on the publisher's thread, inside its transaction (`@event_listener`)."""
    TRANSACTION_PHASE = "transaction_phase"
    """In a phase of the publisher's transaction, after the commit by default, on its thread
    (`@transactional_event_listener`)."""
    ASYNC_AFTER_COMMIT = "async_after_commit"
    """Once the publisher's transaction committed, on a thread of its own, in a transaction of its own; kept in the
    event publication registry until it succeeds (`@application_module_listener`)."""


@dataclass(frozen=True, slots=True)
class ListenerMapping:
    """What a listener marker records on a method: the events it receives and when.

    `phase` and `fallback_execution` belong to a `@transactional_event_listener`: the phase of the publisher's
    transaction it waits for, and whether it receives an event published outside a transaction.
    """

    event_types: tuple[type, ...]
    delivery: Delivery
    phase: TransactionPhase = TransactionPhase.AFTER_COMMIT
    fallback_execution: bool = False


def event_listener(*event_types: type) -> MethodMarker:
    """Marks a method that receives `event_types` at once, inside the publisher's transaction (`@EventListener`).

    Use it for work that must commit or roll back together with the change that caused the event.
    """
    return _mark(event_types, Delivery.IN_TRANSACTION)


def transactional_event_listener(
    *event_types: type, phase: TransactionPhase = TransactionPhase.AFTER_COMMIT, fallback_execution: bool = False
) -> MethodMarker:
    """Marks a method that receives `event_types` in a phase of the transaction they were published in.

    Spring: `@TransactionalEventListener(phase = ..., fallbackExecution = ...)`. By default the phase is
    `AFTER_COMMIT`: use it for effects outside the database, such as notifications, so a rolled-back change never
    reaches anyone, and a failing listener cannot undo the committed change. `BEFORE_COMMIT` runs inside the
    transaction (its writes commit with it, its failure rolls it back); `AFTER_ROLLBACK` only when the transaction
    rolled back; `AFTER_COMPLETION` either way. After the end a failing listener is logged, and its error does not
    reach the publisher. A listener that fails after the commit, or a process that stops before it ran, loses the
    event: for what must arrive, use `@application_module_listener`.

    The event must be published while a transaction runs: one that ended before, as a repository's own transaction
    does, does not count. Without a running transaction the listener is skipped, as in Spring, also in an
    application without a database; `fallback_execution=True` delivers the event at once instead. It never starts a
    transaction, and never delivers after a rollback but in `AFTER_ROLLBACK` or `AFTER_COMPLETION`.

        @component
        class MailOnOrderPlaced:
            @transactional_event_listener(OrderPlaced)
            def send_confirmation(self, event: OrderPlaced) -> None: ...

            @transactional_event_listener(OrderPlaced, phase=TransactionPhase.AFTER_ROLLBACK)
            def report_failure(self, event: OrderPlaced) -> None: ...
    """
    return _mark(event_types, Delivery.TRANSACTION_PHASE, phase=phase, fallback_execution=fallback_execution)


def application_module_listener(*event_types: type, fallback_execution: bool = False) -> MethodMarker:
    """Marks a method that receives `event_types` after the commit, on a thread and in a transaction of its own.

    Spring Modulith's `@ApplicationModuleListener`: `@Async`, `@Transactional(propagation = REQUIRES_NEW)` and
    `@TransactionalEventListener` at once. One module reacts to the facts of another without slowing it down, and
    a failure of one cannot roll back the other. With a database, the publisher's transaction also writes the
    publication into the event publication registry (a transactional outbox): it is deleted in the listener's own
    transaction when the listener succeeds, and delivered again when the listener fails or the process stopped
    first. So the event arrives at least once, and the listener must bear receiving it twice.

        @component
        class InvoiceOnOrderPlaced:
            @application_module_listener(OrderPlaced)
            def create_invoice(self, event: OrderPlaced) -> None: ...

    The event is kept as JSON: a dataclass or a Pydantic model whose fields JSON can hold.

    Like a `@transactional_event_listener`, and Spring Modulith's listener, it hears only an event published while a
    transaction runs: published outside one (no `@transactional` around it, or in an application without a database)
    it is skipped. `fallback_execution=True` hands such an event over at once instead, on the executor, kept in no
    registry, so it is not delivered again when the listener fails.
    """
    return _mark(event_types, Delivery.ASYNC_AFTER_COMMIT, fallback_execution=fallback_execution)


def _mark(
    event_types: tuple[type, ...],
    delivery: Delivery,
    *,
    phase: TransactionPhase = TransactionPhase.AFTER_COMMIT,
    fallback_execution: bool = False,
) -> MethodMarker:
    def record(method: Callable[..., Any]) -> Callable[..., Any]:
        mapping = ListenerMapping(event_types, delivery, phase, fallback_execution)
        setattr(method, LISTENER_MAPPING_ATTRIBUTE, mapping)
        if delivery is Delivery.ASYNC_AFTER_COMMIT:
            setattr(method, APPLICATION_MODULE_LISTENER_ATTRIBUTE, mapping)
        return method

    return record
