from dataclasses import dataclass

from snakeboot.component_scan import application_root
from snakeboot.events import application_event_listener, event_listener
from snakeboot.stereotype import component


@application_root
class UnbuildableListenerApplication:
    """An application with a listener whose dependency cannot be built: it must not start."""


@dataclass(frozen=True)
class SignedUp:
    member: str


@component
class UnreachableMailer:
    """Connects to its mail server when it is built, and that server is down."""

    def __init__(self) -> None:
        raise ConnectionError("The mail server is unreachable.")


@application_event_listener
class WelcomeOnSignUp:
    def __init__(self, mailer: UnreachableMailer) -> None:
        self._mailer = mailer

    @event_listener(SignedUp)
    def welcome(self, event: SignedUp) -> None: ...
