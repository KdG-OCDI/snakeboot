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
    """When a `@scheduled` method runs: every `fixed_rate` from start to start, or `fixed_delay` after each end."""

    fixed_rate: timedelta | None
    fixed_delay: timedelta | None
    initial_delay: timedelta

    def first_run(self, now: float) -> float:
        """The monotonic time of the first run, for a scheduler that starts at `now`."""
        return now + self.initial_delay.total_seconds()

    def next_run(self, started: float, finished: float) -> float:
        """The monotonic time of the next run after one that `started` and `finished`; never in the past."""
        if self.fixed_rate is not None:
            return max(started + self.fixed_rate.total_seconds(), finished)
        delay = self.fixed_delay or timedelta(0)
        return finished + delay.total_seconds()


def scheduled(
    *,
    fixed_rate: timedelta | None = None,
    fixed_delay: timedelta | None = None,
    initial_delay: timedelta = timedelta(0),
) -> MethodMarker:
    """Runs a method of a component periodically, like Spring's `@Scheduled`.

        @injectable
        class AbortExpiredGamesJob:
            def __init__(self, abort_expired_games: AbortExpiredGamesUseCase) -> None: ...

            @scheduled(fixed_delay=timedelta(seconds=2))
            def abort_expired_games(self) -> None: ...

    `fixed_rate` runs it every period from start to start, `fixed_delay` waits the period after each run ends;
    give exactly one. `initial_delay` waits before the first run. The method takes nothing but `self`; one that
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
