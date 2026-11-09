import os
import socket
from collections.abc import Callable
from datetime import UTC, datetime
from typing import override

from snakeboot.scheduler_lock.scheduler_lock_record import SchedulerLockRecords
from snakeboot.scheduling import HeldLock, SchedulerLockMapping, SchedulerLockProvider

type Clock = Callable[[], datetime]


class RepositorySchedulerLockProvider(SchedulerLockProvider):
    """Keeps the scheduler locks in the application's database, like ShedLock's `JdbcTemplateLockProvider`.

    A lock is a row of `snakeboot_scheduler_lock`. Taking it is one UPDATE that holds only while the lock is free, so of
    two processes that try at once, one takes it. Each process names itself by host and process id, unless `holder`
    names it.
    """

    def __init__(self, records: SchedulerLockRecords, clock: Clock | None = None, holder: str | None = None) -> None:
        self._records = records
        self._clock = clock or _now
        self._holder = holder or f"{socket.gethostname()}:{os.getpid()}"

    @override
    def try_lock(self, lock: SchedulerLockMapping) -> HeldLock | None:
        now = self._clock()
        self._records.create_if_missing(lock.name, now)
        if not self._records.take(lock.name, until=now + lock.at_most_for, now=now, holder=self._holder):
            return None
        return _HeldRow(self._records, lock, locked_at=now, holder=self._holder, clock=self._clock)


class _HeldRow(HeldLock):
    def __init__(
        self,
        records: SchedulerLockRecords,
        lock: SchedulerLockMapping,
        *,
        locked_at: datetime,
        holder: str,
        clock: Clock,
    ) -> None:
        self._records = records
        self._lock = lock
        self._locked_at = locked_at
        self._holder = holder
        self._clock = clock

    @override
    def release(self) -> None:
        until = max(self._clock(), self._locked_at + self._lock.at_least_for)
        self._records.release(self._lock.name, until=until, holder=self._holder, locked_at=self._locked_at)


def _now() -> datetime:
    return datetime.now(UTC)
