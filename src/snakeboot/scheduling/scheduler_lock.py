from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Final

from snakeboot.scheduling.scheduled import InvalidScheduledTaskError

SCHEDULER_LOCK_ATTRIBUTE: Final = "__scheduler_lock__"

type MethodMarker = Callable[[Callable[..., Any]], Callable[..., Any]]


@dataclass(frozen=True, slots=True)
class SchedulerLockMapping:
    """What `@scheduler_lock` records on a method: the lock's name and how long it is held."""

    name: str
    at_most_for: timedelta
    at_least_for: timedelta


def scheduler_lock(name: str, *, at_most_for: timedelta, at_least_for: timedelta = timedelta(0)) -> MethodMarker:
    """Lets one process at a time run a `@scheduled` method, like ShedLock's `@SchedulerLock`.

        @scheduled(fixed_rate=timedelta(hours=1))
        @scheduler_lock("hourly-report", at_most_for=timedelta(minutes=50), at_least_for=timedelta(minutes=5))
        def send_hourly_report(self) -> None: ...

    Every replica of a service runs its own scheduler; with the lock, the replica that takes it first runs the method
    and the others skip that turn. `at_most_for` frees the lock of a process that died while it ran; `at_least_for`
    keeps it after a short run, so a replica whose clock is a little behind does not run the same turn again. The
    lock lives in the application's database (`[database]`); a locked method without one stops the start.
    """
    if not name:
        raise InvalidScheduledTaskError("@scheduler_lock names its lock.")
    if at_most_for <= timedelta(0) or not timedelta(0) <= at_least_for <= at_most_for:
        raise InvalidScheduledTaskError(
            f"@scheduler_lock({name!r}) needs a positive at_most_for and an at_least_for between zero and it."
        )
    mapping = SchedulerLockMapping(name, at_most_for, at_least_for)

    def mark(method: Callable[..., Any]) -> Callable[..., Any]:
        setattr(method, SCHEDULER_LOCK_ATTRIBUTE, mapping)
        return method

    return mark


class HeldLock(ABC):
    """A scheduler lock this process holds, like ShedLock's `SimpleLock`."""

    @abstractmethod
    def release(self) -> None:
        """Lets the lock go, but not before its `at_least_for` has passed."""


class SchedulerLockProvider(ABC):
    """Hands out the locks of `@scheduler_lock`, like ShedLock's `LockProvider`; `snakeboot.scheduler_lock` keeps them
    in the application's database."""

    @abstractmethod
    def try_lock(self, lock: SchedulerLockMapping) -> HeldLock | None:
        """Takes `lock` for at most its `at_most_for`, or returns None when another process holds it."""
