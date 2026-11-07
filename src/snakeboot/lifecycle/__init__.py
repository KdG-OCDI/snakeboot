"""Technical library: components that start and stop with the server, like Spring's `SmartLifecycle`.

    class Heartbeat(Lifecycle):                       # a component of the container, by extending Lifecycle
        @override
        def start(self) -> None: ...
        @override
        def stop(self) -> None: ...

    @application_event_listener                       # once everything has started
    class RegisterOnStartup:
        @event_listener(ApplicationReadyEvent)
        def register(self, event: ApplicationReadyEvent) -> None: ...

The lifecycle runs when an ASGI server starts the application (`asgi_application`, which answers uvicorn's
`lifespan`) or when `run_lifecycle` runs it without a web server. Django management commands such as `migrate` and
the tests start nothing. `@scheduled` methods and `@rabbit_listener` methods run through it.
"""

from snakeboot.lifecycle.application_components import ApplicationComponents
from snakeboot.lifecycle.application_lifecycle import ApplicationLifecycle
from snakeboot.lifecycle.application_ready_event import ApplicationReadyEvent
from snakeboot.lifecycle.lifecycle import Lifecycle
from snakeboot.lifecycle.lifecycle_asgi_application import LifecycleAsgiApplication
from snakeboot.lifecycle.task_decorator import TaskDecorator

__all__ = [
    "ApplicationComponents",
    "ApplicationLifecycle",
    "ApplicationReadyEvent",
    "Lifecycle",
    "LifecycleAsgiApplication",
    "TaskDecorator",
]
