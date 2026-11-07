"""`@scheduled` says when a method runs, and refuses a schedule that cannot work."""

from datetime import timedelta

import pytest

from snakeboot.scheduling import InvalidScheduledTaskError, ScheduledMapping, scheduled

SECOND = timedelta(seconds=1)


@pytest.mark.parametrize(
    "arguments",
    [{}, {"fixed_rate": SECOND, "fixed_delay": SECOND}, {"fixed_delay": timedelta(0)}, {"fixed_rate": -SECOND}],
)
def test_a_schedule_needs_exactly_one_positive_period(arguments: dict[str, timedelta]) -> None:
    with pytest.raises(InvalidScheduledTaskError):
        scheduled(**arguments)


def test_a_negative_initial_delay_is_refused() -> None:
    with pytest.raises(InvalidScheduledTaskError):
        scheduled(fixed_delay=SECOND, initial_delay=-SECOND)


def test_a_fixed_delay_counts_from_the_end_of_a_run() -> None:
    mapping = ScheduledMapping(fixed_rate=None, fixed_delay=SECOND, initial_delay=timedelta(0))

    assert mapping.next_run(started=10.0, finished=10.5) == 11.5


def test_a_fixed_rate_counts_from_the_start_and_never_schedules_in_the_past() -> None:
    mapping = ScheduledMapping(fixed_rate=SECOND, fixed_delay=None, initial_delay=timedelta(0))

    assert mapping.next_run(started=10.0, finished=10.5) == 11.0
    assert mapping.next_run(started=10.0, finished=12.0) == 12.0


def test_the_first_run_waits_the_initial_delay() -> None:
    mapping = ScheduledMapping(fixed_rate=SECOND, fixed_delay=None, initial_delay=timedelta(seconds=5))

    assert mapping.first_run(now=100.0) == 105.0
