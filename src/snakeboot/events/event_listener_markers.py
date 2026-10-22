from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

LISTENER_MAPPING_ATTRIBUTE: Final = "__application_event_listener_mapping__"

type MethodMarker = Callable[[Callable[..., Any]], Callable[..., Any]]


@dataclass(frozen=True, slots=True)
class ListenerMapping:
    """What a listener marker records on a method: the events it receives and when."""

    event_types: tuple[type, ...]
    after_commit: bool


def event_listener(*event_types: type) -> MethodMarker:
    """Marks a method that receives `event_types` at once, inside the publisher's transaction (`@EventListener`).

    Use it for work that must commit or roll back together with the change that caused the event.
    """
    return _mark(event_types, after_commit=False)


def transactional_event_listener(*event_types: type) -> MethodMarker:
    """Marks a method that receives `event_types` once the transaction has committed.

    Spring: `@TransactionalEventListener(phase = AFTER_COMMIT)`. Use it for effects outside the
    database, such as notifications: they are delivered through `after_commit`, so a rolled-back
    change never reaches anyone, and a failing listener cannot undo the committed change.
    """
    return _mark(event_types, after_commit=True)


def _mark(event_types: tuple[type, ...], *, after_commit: bool) -> MethodMarker:
    def record(method: Callable[..., Any]) -> Callable[..., Any]:
        setattr(method, LISTENER_MAPPING_ATTRIBUTE, ListenerMapping(event_types, after_commit))
        return method

    return record
