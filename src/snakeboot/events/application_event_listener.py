from typing import Protocol

from wireup import injectable


class ApplicationEventListener(Protocol):
    """The type under which wireup collects every listener, so the publisher receives them all.

    A listener is any class whose methods carry `@event_listener` or `@transactional_event_listener`;
    it does not inherit from this protocol. Wireup injects `Sequence[ApplicationEventListener]`.
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
    and the component scan finds it like every other injectable.
    """
    qualifier = f"{listener_class.__module__}.{listener_class.__qualname__}"
    return injectable(as_type=ApplicationEventListener, qualifier=qualifier)(listener_class)
