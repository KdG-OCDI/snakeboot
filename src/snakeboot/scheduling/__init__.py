"""Technical library: methods that run periodically, like Spring's `@Scheduled`.

    @injectable                                            # a component, like @Component
    class AbortExpiredGamesJob:
        def __init__(self, abort_expired_games: AbortExpiredGamesUseCase) -> None: ...

        @scheduled(fixed_delay=timedelta(seconds=2))       # @Scheduled(fixedDelay = 2000)
        def abort_expired_games(self) -> None: ...

        @scheduled(fixed_rate=timedelta(hours=1))
        @scheduler_lock("hourly-report", at_most_for=timedelta(minutes=50))     # ShedLock's @SchedulerLock
        def send_hourly_report(self) -> None: ...

The scheduler is a `Lifecycle` component: the methods run while an ASGI server serves the application or while
`run_lifecycle` runs it, on one thread, each between fresh database connections. `[scheduling] auto_startup = false`
keeps them from running in a process, such as a web process whose scheduled work runs elsewhere. With
`@scheduler_lock`, one replica at a time runs a method; the lock lives in the database (`snakeboot.scheduler_lock`).
"""

from snakeboot.scheduling.scheduled import InvalidScheduledTaskError, ScheduledMapping, scheduled
from snakeboot.scheduling.scheduler_lock import HeldLock, SchedulerLockMapping, SchedulerLockProvider, scheduler_lock
from snakeboot.scheduling.task_scheduler import TaskScheduler

__all__ = [
    "HeldLock",
    "InvalidScheduledTaskError",
    "ScheduledMapping",
    "SchedulerLockMapping",
    "SchedulerLockProvider",
    "TaskScheduler",
    "scheduled",
    "scheduler_lock",
]
