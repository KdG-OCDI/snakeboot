from dataclasses import dataclass

from snakeboot.component_scan import application_root
from snakeboot.events import event_listener
from snakeboot.stereotype import component, service


@application_root
class UnregisteredListenerApplication:
    """An application whose listener methods sit on plain components, as on Spring's beans: no class declares it
    listens with `@application_event_listener`, and every method still hears its events."""


@dataclass(frozen=True)
class SignedUp:
    member: str


@dataclass(frozen=True)
class SignedOff:
    member: str


@service
class WelcomeService:
    """A service with a listener method."""

    def __init__(self) -> None:
        self.welcomed: list[str] = []

    @event_listener(SignedUp)
    def welcome(self, event: SignedUp) -> None:
        self.welcomed.append(event.member)


@component
class MemberList:
    """A component with two listener methods: it is registered once, each method hears its own events."""

    def __init__(self) -> None:
        self.names: list[str] = []

    @event_listener(SignedUp)
    def add(self, event: SignedUp) -> None:
        self.names.append(event.member)

    @event_listener(SignedOff)
    def remove(self, event: SignedOff) -> None:
        self.names.remove(event.member)
