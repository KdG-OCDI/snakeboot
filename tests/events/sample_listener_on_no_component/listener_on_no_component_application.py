from dataclasses import dataclass

from snakeboot.component_scan import application_root
from snakeboot.events import event_listener


@application_root
class ListenerOnNoComponentApplication:
    """An application with a listener method on a class that is no component: nobody would build it, so it must not
    start."""


@dataclass(frozen=True)
class SignedUp:
    member: str


class Greeter:
    @event_listener(SignedUp)
    def greet(self, event: SignedUp) -> None: ...
