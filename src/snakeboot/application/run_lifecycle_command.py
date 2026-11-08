"""`run_lifecycle`: the application's lifecycle without a web server, like Spring Boot without the web starter.

    python -m myapp run_lifecycle

For a process that only listens and schedules: `@rabbit_listener` and `@scheduled` methods run until the process
receives SIGTERM (`docker stop`) or SIGINT (Ctrl+C), then everything stops cleanly. Its web process turns them off
with `[rabbitmq.listener] auto_startup = false` and `[scheduling] auto_startup = false`.
"""

import signal
import threading
from argparse import Namespace
from types import FrameType
from typing import Final, override

from snakeboot.command_line import CommandLineRunner
from snakeboot.lifecycle.application_lifecycle import ApplicationLifecycle

WAKE_UP_SECONDS: Final = 0.5
"""How often the waiting main thread wakes up: on Windows a wait without timeout cannot be interrupted by Ctrl+C."""


class RunLifecycleCommand(CommandLineRunner, command="run_lifecycle"):
    """Starts the lifecycle (listeners, scheduled tasks) without a web server, until SIGTERM or SIGINT."""

    def __init__(self, application_lifecycle: ApplicationLifecycle) -> None:
        self._lifecycle = application_lifecycle

    @override
    def run(self, arguments: Namespace) -> None:
        stopping = threading.Event()

        def stop(_signal_number: int, _frame: FrameType | None) -> None:
            stopping.set()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        run_until(stopping, self._lifecycle)


def run_until(stopping: threading.Event, lifecycle: ApplicationLifecycle) -> None:
    """Starts `lifecycle`, waits until `stopping` is set, then stops it, also when waiting was interrupted."""
    lifecycle.start()
    try:
        while not stopping.wait(WAKE_UP_SECONDS):
            pass
    finally:
        lifecycle.stop()
