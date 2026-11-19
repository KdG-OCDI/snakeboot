from collections.abc import Callable, Iterable
from typing import Final, Protocol

from wireup import injectable

LISTENER_CLASS_ATTRIBUTE: Final = "__snakeboot_application_event_listener__"
"""Set on a class by `@application_event_listener`: the start-up registers its listener methods."""


class ApplicationEventListener(Protocol):
    """The type under which wireup collects the `@application_event_listener` classes for the start-up.

    A listener is any component whose methods carry `@event_listener`, `@transactional_event_listener` or
    `@application_module_listener`; it does not inherit from this protocol. Wireup injects
    `Sequence[ApplicationEventListener]` into the `EventListenerMethodProcessor`, not into the publisher, so a listener
    may depend on what publishes; the listener methods of the other components the start-up finds by the scan.
    """


class InvalidApplicationEventListenerError(TypeError):
    """Raised at start-up when a class or method cannot listen to application events.

    Like a broken controller, a broken listener must stop the application from starting,
    not fail silently at the first event.
    """


def application_event_listener[C: type](listener_class: C) -> C:
    """Declares a listener: a component whose marked methods receive published events.

    Not needed: like Spring, which finds `@EventListener` methods on any bean, the start-up registers the listener
    methods of every component, so `@component` (or `@service`) on the class does. This decorator stays for the
    applications that have it, and goes in a later minor release. It registers the class as an
    `ApplicationEventListener` (qualified by its name, so several can exist), which the component scan finds like
    every other component.

        @component
        class InvoiceOnOrderPlaced:
            def __init__(self, events: ApplicationEventPublisher) -> None:
                self._events = events

            @event_listener(OrderPlaced)
            def create_invoice(self, event: OrderPlaced) -> None:
                self._events.publish(InvoiceCreated(event.order_id))

    A listener method returns None. Spring publishes what a synchronous `@EventListener` returns as a next event;
    snakeboot does not, and refuses a listener method that declares another return type: publish a follow-up event
    through the `ApplicationEventPublisher`, as above. Its constructor may inject any
    component, a use case that publishes events included; the application builds it while it starts.
    """
    qualifier = f"{listener_class.__module__}.{listener_class.__qualname__}"
    setattr(listener_class, LISTENER_CLASS_ATTRIBUTE, True)
    return injectable(as_type=ApplicationEventListener, qualifier=qualifier)(listener_class)


def listening_components(owners: Iterable[tuple[str, type]], component_of: Callable[[type], object]) -> list[object]:
    """Returns the components whose listener methods the start-up registers besides the `@application_event_listener`s.

    `owners` are the scanned listener methods, by `module.Class.method`, and their classes; `component_of` returns
    the container's component of a class, or raises `LookupError` for a class that is none. Like Spring, which finds
    an `@EventListener` on any bean, a listener method on a `@component` or a `@service` hears its events. One on a
    class that is no component stops the start, as an `@scheduled` method does there, instead of never hearing one.
    """
    components: dict[type, object] = {}
    for name, owner in owners:
        if getattr(owner, LISTENER_CLASS_ATTRIBUTE, False) or owner in components:
            continue
        try:
            components[owner] = component_of(owner)
        except LookupError as error:
            raise InvalidApplicationEventListenerError(
                f"{name} listens to events, but {owner.__qualname__} is no component: add @component."
            ) from error
    return list(components.values())
