"""`run_lifecycle`: the application's lifecycle without a web server, like Spring Boot without the web starter.

    python -m myapp run_lifecycle

For a process that only listens and schedules: `@rabbit_listener` and `@scheduled` methods run until the process
receives SIGTERM (`docker stop`) or SIGINT (Ctrl+C), then everything stops cleanly. Its web process turns them off
with `[rabbitmq.listener] auto_startup = false` and `[scheduling] auto_startup = false`.
"""

import signal
import threading
from types import FrameType
from typing import Any, Final, override

from django.core.management.base import BaseCommand
from wireup import Injected
from wireup.integration.django import inject_app

from snakeboot.lifecycle.application_lifecycle import ApplicationLifecycle

WAKE_UP_SECONDS: Final = 0.5
"""How often the waiting main thread wakes up: on Windows a wait without timeout cannot be interrupted by Ctrl+C."""


class Command(BaseCommand):
    """Runs the lifecycle until SIGTERM or SIGINT. Django requires the name `Command`."""

    help = "Starts the lifecycle (listeners, scheduled tasks) without a web server, until SIGTERM or SIGINT."

    @override
    @inject_app
    def handle(self, *args: Any, application_lifecycle: Injected[ApplicationLifecycle], **options: Any) -> None:
        stopping = threading.Event()

        def stop(_signal_number: int, _frame: FrameType | None) -> None:
            stopping.set()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        run_until(stopping, application_lifecycle)


def run_until(stopping: threading.Event, lifecycle: ApplicationLifecycle) -> None:
    """Starts `lifecycle`, waits until `stopping` is set, then stops it, also when waiting was interrupted."""
    lifecycle.start()
    try:
        while not stopping.wait(WAKE_UP_SECONDS):
            pass
    finally:
        lifecycle.stop()
