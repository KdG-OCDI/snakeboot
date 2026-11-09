from abc import ABC, abstractmethod
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Final, override

POOL_SIZE: Final = 8
"""How many threads the application's executor has, like Spring Boot's `spring.task.execution.pool.core-size`."""


class TaskExecutor(ABC):
    """Runs a piece of work, like Spring's `TaskExecutor`: the `@application_module_listener` methods run on one."""

    @abstractmethod
    def execute(self, task: Callable[[], None]) -> None:
        """Runs `task`, now or later; what it raises is its own to handle."""


class ThreadPoolTaskExecutor(TaskExecutor):
    """Runs every piece of work on a pool of threads, like Spring Boot's `applicationTaskExecutor`.

    The threads start when there is work. `shutdown` lets the work in hand and the work waiting finish first.
    """

    def __init__(self, pool_size: int = POOL_SIZE) -> None:
        self._pool = ThreadPoolExecutor(max_workers=pool_size, thread_name_prefix="snakeboot-task")

    @override
    def execute(self, task: Callable[[], None]) -> None:
        self._pool.submit(task)

    def shutdown(self) -> None:
        """Waits for the work in hand and the work waiting, and starts no other."""
        self._pool.shutdown(wait=True)


class SyncTaskExecutor(TaskExecutor):
    """Runs every piece of work at once, on the caller's thread, like Spring's `SyncTaskExecutor`.

    A test starts the application with it, so what an `@application_module_listener` did is there when the call that
    published the event returns.
    """

    @override
    def execute(self, task: Callable[[], None]) -> None:
        task()
