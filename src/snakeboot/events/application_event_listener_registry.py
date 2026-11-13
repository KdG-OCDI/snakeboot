import inspect
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Final

from snakeboot.events.application_event_listener import InvalidApplicationEventListenerError
from snakeboot.events.event_listener_markers import LISTENER_MAPPING_ATTRIBUTE, ListenerMapping

_SELF_AND_EVENT: Final = 2


@dataclass(frozen=True, slots=True)
class ListenerMethod:
    """One listener method, named `module.Class.method`, and the events it receives.

    What Spring's `ApplicationListenerMethodAdapter` makes of an `@EventListener` method.
    """

    name: str
    receive: Callable[[object], None]
    mapping: ListenerMapping


class ApplicationEventListenerRegistry:
    """The listener methods the publisher hands events to, like the listeners Spring's `ApplicationEventMulticaster`
    keeps for the publisher.

    It starts empty and the start-up fills it once the container is built (`EventListenerMethodProcessor`), so the
    publisher depends on no listener, and a listener may depend on a use case that publishes events. The methods are
    kept in a stable order, by name. A listener without listener methods, or with one that is async or takes anything
    but the event, is refused.
    """

    def __init__(self) -> None:
        self._methods: tuple[ListenerMethod, ...] = ()
        self._lock = threading.Lock()

    @property
    def methods(self) -> tuple[ListenerMethod, ...]:
        """Every listener method registered so far, by name."""
        return self._methods

    def register(self, listeners: Iterable[object]) -> list[ListenerMethod]:
        """Adds the listener methods of `listeners` and returns them.

        Raises `InvalidApplicationEventListenerError`, and adds none, when one of `listeners` cannot listen.
        """
        added = [method for listener in listeners for method in _methods_of(listener)]
        with self._lock:
            self._methods = tuple(sorted((*self._methods, *added), key=lambda method: method.name))
        return added

    def receiving(self, event: object) -> list[ListenerMethod]:
        """Returns the methods that asked for the type of `event` or one of its base classes, by name."""
        return [method for method in self._methods if isinstance(event, method.mapping.event_types)]


def _methods_of(listener: object) -> list[ListenerMethod]:
    listener_class = type(listener)
    methods = [
        ListenerMethod(
            name=f"{listener_class.__module__}.{listener_class.__qualname__}.{name}",
            receive=_receiver(listener, name, method),
            mapping=mapping,
        )
        for name, method in inspect.getmembers(listener_class, inspect.isfunction)
        if (mapping := getattr(method, LISTENER_MAPPING_ATTRIBUTE, None)) is not None
    ]
    if not methods:
        raise InvalidApplicationEventListenerError(f"{listener_class.__name__} has no listener methods.")
    return methods


def _receiver(listener: object, name: str, method: Callable[..., Any]) -> Callable[[object], None]:
    owner = f"{type(listener).__name__}.{name}"
    if inspect.iscoroutinefunction(method):
        raise InvalidApplicationEventListenerError(f"{owner} is async; listeners are synchronous.")
    if len(inspect.signature(method).parameters) != _SELF_AND_EVENT:
        raise InvalidApplicationEventListenerError(f"{owner} must take exactly one argument: the event.")
    receive: Callable[[object], None] = getattr(listener, name)
    return receive
