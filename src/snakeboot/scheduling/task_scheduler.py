import heapq
import inspect
import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Final, override

from snakeboot.component_scan import MarkedMethod
from snakeboot.lifecycle.application_components import ApplicationComponents
from snakeboot.lifecycle.lifecycle import Lifecycle
from snakeboot.lifecycle.task_decorator import TaskDecorator
from snakeboot.scheduling.scheduled import SCHEDULED_MAPPING_ATTRIBUTE, InvalidScheduledTaskError, ScheduledMapping

logger = logging.getLogger(__name__)

SHUTDOWN_SECONDS: Final = 5.0
"""How long `stop` waits for the method in hand to finish, like Spring's await-termination period."""

_ONLY_SELF: Final = 1


@dataclass(frozen=True, slots=True)
class ScheduledTask:
    """One `@scheduled` method, bound to its component, and when it runs."""

    name: str
    run: Callable[[], None]
    mapping: ScheduledMapping


@dataclass(order=True, slots=True)
class _Turn:
    due: float
    order: int
    task: ScheduledTask = field(compare=False)


class TaskScheduler(Lifecycle, component=False):
    """Runs every `@scheduled` method of the application on one thread, like Spring's `ThreadPoolTaskScheduler`.

    `start` finds the methods and their components; a method that cannot run as declared stops the start-up, even
    when `auto_startup` is off, so a broken schedule shows in every process. Without methods, or with `auto_startup`
    off, no thread starts. A method that raises is logged and keeps its schedule. `stop` lets the method in hand
    finish (for at most `SHUTDOWN_SECONDS`) and starts no other.

    `snakeboot.scheduling.task_scheduler_injectable` registers it with wireup; tests build it with stand-ins.
    """

    def __init__(self, components: ApplicationComponents, task_decorator: TaskDecorator, *, auto_startup: bool) -> None:
        self._components = components
        self._task_decorator = task_decorator
        self._auto_startup = auto_startup
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        """Whether the scheduler's thread runs."""
        return self._thread is not None and self._thread.is_alive()

    @override
    def start(self) -> None:
        tasks = [
            self._task_of(marked)
            for marked in self._components.methods_marked(SCHEDULED_MAPPING_ATTRIBUTE, ScheduledMapping)
        ]
        if not tasks or not self._auto_startup:
            return
        self._stopping.clear()
        self._thread = threading.Thread(target=self._run, args=(tasks,), name="snakeboot-scheduler", daemon=True)
        self._thread.start()

    @override
    def stop(self) -> None:
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(timeout=SHUTDOWN_SECONDS)
            self._thread = None

    def _task_of(self, marked: MarkedMethod[ScheduledMapping]) -> ScheduledTask:
        if inspect.iscoroutinefunction(marked.method):
            raise InvalidScheduledTaskError(f"{marked.name} is async; scheduled methods are synchronous.")
        if len(inspect.signature(marked.method).parameters) != _ONLY_SELF:
            raise InvalidScheduledTaskError(f"{marked.name} must take nothing but self.")
        try:
            component: object = self._components.get(marked.owner)
        except LookupError as error:
            raise InvalidScheduledTaskError(
                f"{marked.name} is @scheduled, but {marked.owner.__qualname__} is no component: add @injectable."
            ) from error
        run: Callable[[], None] = getattr(component, marked.method.__name__)
        return ScheduledTask(marked.name, self._task_decorator.decorate(run), marked.mapping)

    def _run(self, tasks: Sequence[ScheduledTask]) -> None:
        now = time.monotonic()
        turns = [_Turn(task.mapping.first_run(now), order, task) for order, task in enumerate(tasks)]
        heapq.heapify(turns)
        while not self._stopping.wait(max(0.0, turns[0].due - time.monotonic())):
            turn = heapq.heappop(turns)
            started = time.monotonic()
            _run_logging_failures(turn.task)
            turn.due = turn.task.mapping.next_run(started, time.monotonic())
            heapq.heappush(turns, turn)


def _run_logging_failures(task: ScheduledTask) -> None:
    try:
        task.run()
    except Exception:
        logger.exception("The scheduled method %s failed; it runs again at its next turn", task.name)
