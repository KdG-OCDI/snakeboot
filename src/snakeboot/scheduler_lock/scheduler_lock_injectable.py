"""Registers the provider of the `@scheduler_lock` locks with wireup.

`snakeboot.boot` adds this module, and the one of its table, to the container when the application has `[database]`,
like ShedLock with its JDBC provider.
"""

from wireup import injectable

from snakeboot.scheduler_lock.repository_scheduler_lock_provider import RepositorySchedulerLockProvider
from snakeboot.scheduler_lock.scheduler_lock_record import SchedulerLockRecords
from snakeboot.scheduling import SchedulerLockProvider


@injectable(as_type=SchedulerLockProvider)
def scheduler_lock_provider(records: SchedulerLockRecords) -> SchedulerLockProvider:
    """Provides the locks in the application's database."""
    return RepositorySchedulerLockProvider(records)
