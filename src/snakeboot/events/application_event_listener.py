from collections.abc import Iterable
from typing import Final, Protocol

from wireup import injectable

LISTENER_CLASS_ATTRIBUTE: Final = "__snakeboot_application_event_listener__"
"""Set on a class by `@application_event_listener`: the start-up registers its listener methods."""


class ApplicationEventListener(Protocol):
    """The type under which wireup collects every listener, so the start-up registers them all with the publisher.

    A listener is any class whose methods carry `@event_listener` or `@transactional_event_listener`;
    it does not inherit from this protocol. Wireup injects `Sequence[ApplicationEventListener]` into the
    `EventListenerMethodProcessor`, not into the publisher, so a listener may depend on what publishes.
    """


class InvalidApplicationEventListenerError(TypeError):
    """Raised at start-up when a class or method cannot listen to application events.

    Like a broken controller, a broken listener must stop the application from starting,
    not fail silently at the first event.
    """


def application_event_listener[C: type](listener_class: C) -> C:
    """Declares a listener: a wireup singleton whose marked methods receive published events.

    Spring finds `@EventListener` methods on any bean. Here the class says it listens, so wireup
    registers it as an `ApplicationEventListener` (qualified by its name, so several can exist)
    and the component scan finds it like every other injectable; a listener method on a class without this
    declaration stops the start.

        @application_event_listener
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


def refuse_listener_methods_nobody_registers(owners: Iterable[tuple[str, type]]) -> None:
    """Stops the start on a listener method whose class is no `@application_event_listener`.

    `owners` are the scanned listener methods, by `module.Class.method`, and their classes. Spring finds an
    `@EventListener` on any bean; here the class declares that it listens, so a marked method on a `@service` would
    never hear an event. Refused at the start instead of silently losing the reaction.
    """
    for name, owner in owners:
        if not getattr(owner, LISTENER_CLASS_ATTRIBUTE, False):
            raise InvalidApplicationEventListenerError(
                f"{name} listens to events, but {owner.__qualname__} is no @application_event_listener: declare the "
                "class with @application_event_listener, or nobody registers the method."
            )
