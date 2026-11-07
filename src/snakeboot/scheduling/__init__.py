"""Technical library: methods that run periodically, like Spring's `@Scheduled`.

    @injectable                                            # a component, like @Component
    class AbortExpiredGamesJob:
        def __init__(self, abort_expired_games: AbortExpiredGamesUseCase) -> None: ...

        @scheduled(fixed_delay=timedelta(seconds=2))       # @Scheduled(fixedDelay = 2000)
        def abort_expired_games(self) -> None: ...

The scheduler is a `Lifecycle` component: the methods run while an ASGI server serves the application or while
`run_lifecycle` runs it, on one thread, each between fresh database connections. `[scheduling] auto_startup = false`
keeps them from running in a process, such as a web process whose scheduled work runs elsewhere.
"""

from snakeboot.scheduling.scheduled import InvalidScheduledTaskError, ScheduledMapping, scheduled
from snakeboot.scheduling.task_scheduler import TaskScheduler

__all__ = ["InvalidScheduledTaskError", "ScheduledMapping", "TaskScheduler", "scheduled"]
