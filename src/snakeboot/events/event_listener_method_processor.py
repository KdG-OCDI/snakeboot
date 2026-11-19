from collections.abc import Iterable

from snakeboot.events.application_event_publisher import ApplicationEventPublisher


class EventListenerMethodProcessor:
    """Registers every listener with the publisher once the container is built, like Spring's
    `EventListenerMethodProcessor` once every singleton exists: the `@application_event_listener`s wireup collects, and
    the other components with listener methods that the start-up `include`s.

    The publisher depends on no listener, so a listener may inject any component, a use case that publishes events
    included: wireup builds the listeners, with what they depend on, to build this processor instead. The application
    context builds it and calls `register_listeners` while the application starts, so a listener that cannot be
    built, or cannot listen, stops the start-up instead of the first event.
    """

    def __init__(self, publisher: ApplicationEventPublisher, listeners: Iterable[object]) -> None:
        self._publisher = publisher
        self._listeners = list(listeners)
        self._registered = False

    @property
    def listeners(self) -> list[object]:
        """Every listener it registers."""
        return list(self._listeners)

    def include(self, listeners: Iterable[object]) -> None:
        """Adds components with listener methods, before `register_listeners`; one it has already is left out."""
        self._listeners += [listener for listener in listeners if all(listener is not had for had in self._listeners)]

    def register_listeners(self) -> None:
        """Hands every listener to the publisher, the first time it is called."""
        if not self._registered:
            self._publisher.register(self._listeners)
            self._registered = True
