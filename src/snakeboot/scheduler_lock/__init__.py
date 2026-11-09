"""Technical library: the locks of `@scheduler_lock` in the application's database, like ShedLock.

    @scheduled(fixed_rate=timedelta(hours=1))
    @scheduler_lock("hourly-report", at_most_for=timedelta(minutes=50))
    def send_hourly_report(self) -> None: ...              # one replica per turn

With `[database]`, a lock is a row of `snakeboot_scheduler_lock`, taken with one conditional UPDATE. Run
`make_migration` once to add the table to the application's migrations. It knows `snakeboot.scheduling` and
`snakeboot.data`, but no persistence framework.
"""

from snakeboot.scheduler_lock.repository_scheduler_lock_provider import RepositorySchedulerLockProvider
from snakeboot.scheduler_lock.scheduler_lock_record import SchedulerLockRecord, SchedulerLockRecords

__all__ = ["RepositorySchedulerLockProvider", "SchedulerLockRecord", "SchedulerLockRecords"]
