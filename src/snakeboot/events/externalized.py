from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Final

EXTERNALIZED_ATTRIBUTE: Final = "__snakeboot_externalized__"
"""The mark `@externalized` leaves on an event class: where its events go. The event publication registry's table is
needed by it, as by an `@application_module_listener`."""

_SEPARATOR: Final = "::"


class InvalidExternalizationError(TypeError):
    """Raised when `@externalized` names no target and key, or no broker sends the events it marks."""


@dataclass(frozen=True, slots=True)
class ExternalizationTarget:
    """Where the events of an `@externalized` class go: the target (RabbitMQ's exchange) and the key (its routing
    key), like Spring Modulith's `RoutingTarget`."""

    target: str
    key: str


class EventExternalization:
    """The base class of a broker's listener that sends the `@externalized` events, like Spring Modulith's
    `EventExternalizer`; the start-up refuses `@externalized` events when no listener of this kind is registered."""


def externalized[C: type](target: str) -> Callable[[C], C]:
    """Sends every event of the class to a broker as well, like Spring Modulith's `@Externalized("target::key")`.

        @externalized("auctions::auction.closed")      # exchange `auctions`, routing key `auction.closed`
        @dataclass(frozen=True)
        class AuctionClosed:
            auction_id: UUID
            winning_bid: Decimal

    The event stays an application event: the listeners of the application hear it as before. Besides, once the
    transaction that published it committed, the binding sends it as JSON, through the event publication registry,
    so it reaches the broker at least once, also when the broker was down for a while; its message id is the
    publication's, the same each time it is sent again, so a receiver recognises a duplicate. With `[rabbitmq]` the
    target is a topic exchange and the key a routing key; another application listens with `@rabbit_listener`, or
    replays the history with `@rabbit_stream_listener`. Without `[rabbitmq]` the start-up stops: nothing would send
    the events. The class belongs to the component scan, and is a dataclass or a Pydantic model, which the registry
    keeps as JSON; another class stops the start. A subclass goes where its base class goes.

    Like Spring Modulith, it sends what a transaction published. Unlike Spring Modulith, an event published outside a
    transaction, as in an application without a database, is sent at once instead of not at all: kept in no registry,
    so it is lost when the broker is down.
    """
    exchange, separator, key = target.partition(_SEPARATOR)
    if not exchange or not separator or not key:
        raise InvalidExternalizationError(f"@externalized({target!r}) names a target and a key: 'exchange::key'.")
    destination = ExternalizationTarget(exchange, key)

    def mark(event_type: C) -> C:
        setattr(event_type, EXTERNALIZED_ATTRIBUTE, destination)
        return event_type

    return mark


def externalization_target(event: object) -> ExternalizationTarget:
    """Returns where `event` goes: the target its class, or a base class, declared with `@externalized`."""
    destination = getattr(type(event), EXTERNALIZED_ATTRIBUTE, None)
    if not isinstance(destination, ExternalizationTarget):
        raise InvalidExternalizationError(f"{type(event).__qualname__} is not @externalized.")
    return destination


def refuse_externalized_events_nobody_sends(externalized_types: Iterable[type], listeners: Iterable[object]) -> None:
    """Stops the start on `@externalized` events when no registered listener is an `EventExternalization`.

    `externalized_types` are the scanned classes `@externalized` marked, `listeners` every registered listener. An
    application without a broker's binding (`[rabbitmq]`) would never send them: refused at the start instead of
    silently keeping the events to itself.
    """
    names = sorted(event_type.__qualname__ for event_type in externalized_types)
    if names and not any(isinstance(listener, EventExternalization) for listener in listeners):
        raise InvalidExternalizationError(
            f"{', '.join(names)} @externalized, but no broker sends them: add the table [rabbitmq] to the "
            "configuration, or leave out @externalized."
        )
