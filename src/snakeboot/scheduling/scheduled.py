from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Final

SCHEDULED_MAPPING_ATTRIBUTE: Final = "__scheduled_mapping__"

type MethodMarker = Callable[[Callable[..., Any]], Callable[..., Any]]


class InvalidScheduledTaskError(TypeError):
    """Raised while the application starts when a `@scheduled` method cannot run as declared.

    Like a broken controller, a broken schedule must stop the start-up, not fail silently at the first run.
    """


@dataclass(frozen=True, slots=True)
class ScheduledMapping:
    """When a `@scheduled` method runs: every `fixed_rate` on a fixed schedule, or `fixed_delay` after each end."""

    fixed_rate: timedelta | None
    fixed_delay: timedelta | None
    initial_delay: timedelta

    def first_run(self, now: float) -> float:
        """The monotonic time of the first run, for a scheduler that starts at `now`."""
        return now + self.initial_delay.total_seconds()

    def next_run(self, due: float, finished: float) -> float:
        """The monotonic time of the next run after the one that was `due` and `finished`.

        With `fixed_rate`, the period after the time the run was due, not after its late start: the schedule stays
        anchored to the first run, as Java's `ScheduledExecutorService.scheduleAtFixedRate` keeps it. A time already
        past is a turn that is overdue: the scheduler runs it at once, one after the other until the schedule caught
        up, never two runs of the same method at the same time. With `fixed_delay`, the period after the run finished.
        """
        if self.fixed_rate is not None:
            return due + self.fixed_rate.total_seconds()
        delay = self.fixed_delay or timedelta(0)
        return finished + delay.total_seconds()


def scheduled(
    *,
    fixed_rate: timedelta | None = None,
    fixed_delay: timedelta | None = None,
    initial_delay: timedelta = timedelta(0),
) -> MethodMarker:
    """Runs a method of a component periodically, like Spring's `@Scheduled`.

        @component
        class AbortExpiredGamesJob:
            def __init__(self, abort_expired_games: AbortExpiredGamesUseCase) -> None: ...

            @scheduled(fixed_delay=timedelta(seconds=2))
            def abort_expired_games(self) -> None: ...

    `fixed_rate` runs it every period on a fixed schedule from its first run, `fixed_delay` waits the period after each
    run ends; give exactly one. A fixed rate is no promise of punctuality: when a run, or another scheduled method on
    the one thread, takes longer than the period, the turns it delayed run back to back once the thread is free, as
    with Spring's `ThreadPoolTaskScheduler` (a first run of 25 seconds every 10 seconds starts at 0, 25, 26, 30, ...).
    `initial_delay` waits before the first run. The method takes nothing but `self`; one that
    raises is logged and runs again at its next turn. All scheduled methods share one thread, like Spring Boot's
    scheduler with its default pool size of one.
    """
    if (fixed_rate is None) == (fixed_delay is None):
        raise InvalidScheduledTaskError("@scheduled needs exactly one of fixed_rate and fixed_delay.")
    period = fixed_rate or fixed_delay or timedelta(0)
    if period <= timedelta(0) or initial_delay < timedelta(0):
        raise InvalidScheduledTaskError("@scheduled needs a positive period and an initial delay that is not negative.")
    mapping = ScheduledMapping(fixed_rate=fixed_rate, fixed_delay=fixed_delay, initial_delay=initial_delay)

    def mark(method: Callable[..., Any]) -> Callable[..., Any]:
        setattr(method, SCHEDULED_MAPPING_ATTRIBUTE, mapping)
        return method

    return mark
