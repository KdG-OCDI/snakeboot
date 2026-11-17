from abc import ABC
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

EXTERNALIZED_ATTRIBUTE: Final = "__snakeboot_externalized__"
"""The mark `@externalized` leaves on an event class: where its events go. The event publication registry's table is
needed by it, as by an `@application_module_listener`."""

_SEPARATOR: Final = "::"


class InvalidExternalizationError(TypeError):
    """Raised when `@externalized` names no target and key, or the registry cannot keep the event it marks."""


@dataclass(frozen=True, slots=True)
class ExternalizationTarget:
    """Where the events of an `@externalized` class go: the target (RabbitMQ's exchange) and the key (its routing
    key), like Spring Modulith's `RoutingTarget`."""

    target: str
    key: str


class ExternalizedEvent(ABC):  # noqa: B024  # reason: a virtual base class: @externalized registers the event classes
    """The type of every event whose class is `@externalized`, so one listener receives them all.

    No event inherits from it: `@externalized` registers the class, so `isinstance(event, ExternalizedEvent)` holds.
    The binding of a broker listens to it, as Spring Modulith's `EventExternalizer` listens to every event.
    """


def externalized[C: type](target: str) -> Callable[[C], C]:
    """Sends every event of the class to a broker as well, like Spring Modulith's `@Externalized("target::key")`.

        @externalized("auctions::auction.closed")      # exchange `auctions`, routing key `auction.closed`
        @dataclass(frozen=True)
        class AuctionClosed:
            auction_id: UUID
            winning_bid: Decimal

    The event stays an application event: the listeners of the application hear it as before. Besides, once the
    transaction that published it committed, the binding sends it as JSON, through the event publication registry,
    so it reaches the broker at least once, also when the broker was down for a while. With `[rabbitmq]` the target
    is a topic exchange and the key a routing key; another application listens with `@rabbit_listener`, or replays
    the history with `@rabbit_stream_listener`. The event is a dataclass or a Pydantic model, which the registry keeps
    as JSON; another class stops the start.

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
        ExternalizedEvent.register(event_type)
        return event_type

    return mark


def externalization_target(event: object) -> ExternalizationTarget:
    """Returns where `event` goes: the target its class, or a base class, declared with `@externalized`."""
    destination = getattr(type(event), EXTERNALIZED_ATTRIBUTE, None)
    if not isinstance(destination, ExternalizationTarget):
        raise InvalidExternalizationError(f"{type(event).__qualname__} is not @externalized.")
    return destination
