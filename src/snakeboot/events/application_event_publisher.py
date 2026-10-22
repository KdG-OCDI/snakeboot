import inspect
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import partial
from typing import Any, Final

from snakeboot.events.application_event_listener import InvalidApplicationEventListenerError
from snakeboot.events.event_listener_markers import LISTENER_MAPPING_ATTRIBUTE, ListenerMapping
from snakeboot.transaction import after_commit

_SELF_AND_EVENT: Final = 2


@dataclass(frozen=True, slots=True)
class _Subscription:
    """One listener method and the events it receives."""

    name: str
    receive: Callable[[object], None]
    mapping: ListenerMapping

    def deliver(self, event: object) -> None:
        if self.mapping.after_commit:
            after_commit(partial(self.receive, event))
        else:
            self.receive(event)


class ApplicationEventPublisher:
    """Hands each event to the listener methods that asked for its type (Spring's `ApplicationEventPublisher`).

    It is the Observer pattern for facts: the use case that publishes does not know who
    reacts, and a new reaction is a new listener, not a change to the use case. Delivery is
    synchronous and in-process, in a stable order (by listener name). A listener for a base
    class (`WorkshopEvent`) receives every subclass.

    The library registers it with wireup (`application_event_publisher_injectable`), connected
    to every listener wireup found, or to none; tests build it with the listeners they need.
    """

    def __init__(self, listeners: Iterable[object]) -> None:
        self._subscriptions = sorted(
            (subscription for listener in listeners for subscription in self._subscriptions_of(listener)),
            key=lambda subscription: subscription.name,
        )

    def publish(self, event: object) -> None:
        """Delivers `event` to every listener method for its type; immediately or after the commit."""
        for subscription in self._subscriptions:
            if isinstance(event, subscription.mapping.event_types):
                subscription.deliver(event)

    def publish_all(self, events: Iterable[object]) -> None:
        """Publishes `events` in the order they happened."""
        for event in events:
            self.publish(event)

    def _subscriptions_of(self, listener: object) -> list[_Subscription]:
        listener_class = type(listener)
        subscriptions = [
            _Subscription(
                name=f"{listener_class.__module__}.{listener_class.__qualname__}.{name}",
                receive=self._receiver(listener, name, method),
                mapping=mapping,
            )
            for name, method in inspect.getmembers(listener_class, inspect.isfunction)
            if (mapping := getattr(method, LISTENER_MAPPING_ATTRIBUTE, None)) is not None
        ]
        if not subscriptions:
            raise InvalidApplicationEventListenerError(f"{listener_class.__name__} has no listener methods.")
        return subscriptions

    def _receiver(self, listener: object, name: str, method: Callable[..., Any]) -> Callable[[object], None]:
        owner = f"{type(listener).__name__}.{name}"
        if inspect.iscoroutinefunction(method):
            raise InvalidApplicationEventListenerError(f"{owner} is async; listeners are synchronous.")
        if len(inspect.signature(method).parameters) != _SELF_AND_EVENT:
            raise InvalidApplicationEventListenerError(f"{owner} must take exactly one argument: the event.")
        receive: Callable[[object], None] = getattr(listener, name)
        return receive
