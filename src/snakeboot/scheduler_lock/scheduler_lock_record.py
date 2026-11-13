"""The table of the scheduler locks, in snakeboot's own terms: an entity and its repository.

Every application with `[database]` maps it, but its table is part of the schema only once the application has a
`@scheduler_lock` method: then `make_migration` writes it into the application's migrations, like the table ShedLock's
JDBC provider asks for once ShedLock is there.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Protocol

from snakeboot.data import Column, CrudRepository, Id, entity, query
from snakeboot.scheduling.scheduler_lock import SCHEDULER_LOCK_ATTRIBUTE


@entity("snakeboot_scheduler_lock", needed_by=SCHEDULER_LOCK_ATTRIBUTE)
@dataclass
class SchedulerLockRecord:
    """One lock of `@scheduler_lock`: held until `lock_until`, since `locked_at`, by `locked_by` (host and process)."""

    name: Annotated[str, Id(), Column(length=200)]
    lock_until: datetime
    locked_at: datetime
    locked_by: Annotated[str, Column(length=255)]


class SchedulerLockRecords(CrudRepository[SchedulerLockRecord, str], Protocol):
    """The locks, taken and let go with one statement each, so two processes never both take one."""

    @query(
        "INSERT INTO snakeboot_scheduler_lock (name, lock_until, locked_at, locked_by) "
        "VALUES (:name, :now, :now, '') ON CONFLICT (name) DO NOTHING",
        modifying=True,
    )
    def create_if_missing(self, name: str, now: datetime) -> int:
        """Adds the lock `name`, free from `now`, unless it is there already."""
        ...

    @query(
        "UPDATE snakeboot_scheduler_lock SET lock_until = :until, locked_at = :now, locked_by = :holder "
        "WHERE name = :name AND lock_until <= :now",
        modifying=True,
    )
    def take(self, name: str, *, until: datetime, now: datetime, holder: str) -> int:
        """Takes the lock `name` until `until` when it is free at `now`; returns 1 when taken, 0 when held elsewhere."""
        ...

    @query(
        "UPDATE snakeboot_scheduler_lock SET lock_until = :until "
        "WHERE name = :name AND locked_by = :holder AND locked_at = :locked_at",
        modifying=True,
    )
    def release(self, name: str, *, until: datetime, holder: str, locked_at: datetime) -> int:
        """Holds the lock `name` that `holder` took at `locked_at` only until `until`."""
        ...
