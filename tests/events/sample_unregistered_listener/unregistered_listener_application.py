from dataclasses import dataclass

from snakeboot.component_scan import application_root
from snakeboot.events import event_listener
from snakeboot.stereotype import service


@application_root
class UnregisteredListenerApplication:
    """An application with a listener method on a service that does not declare it listens: it must not start."""


@dataclass(frozen=True)
class SignedUp:
    member: str


@service
class WelcomeService:
    @event_listener(SignedUp)
    def welcome(self, event: SignedUp) -> None: ...
