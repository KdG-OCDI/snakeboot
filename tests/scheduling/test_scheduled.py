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

    assert mapping.next_run(due=9.0, finished=10.5) == 11.5


def test_a_fixed_rate_keeps_to_its_schedule_from_the_time_a_run_was_due() -> None:
    mapping = ScheduledMapping(fixed_rate=SECOND, fixed_delay=None, initial_delay=timedelta(0))

    assert mapping.next_run(due=10.0, finished=10.5) == 11.0
    assert mapping.next_run(due=10.0, finished=12.0) == 11.0, "overdue: the scheduler runs it at once"


def start_times(mapping: ScheduledMapping, durations: list[float]) -> list[float]:
    """The start of each run on a scheduler of one thread that runs every overdue turn at once."""
    starts, due, free_at = [], mapping.first_run(0.0), 0.0
    for duration in durations:
        start = max(due, free_at)
        starts.append(start)
        free_at = start + duration
        due = mapping.next_run(due, free_at)
    return starts


def test_after_a_long_run_a_fixed_rate_catches_up_one_turn_after_the_other() -> None:
    every_ten_seconds = ScheduledMapping(fixed_rate=timedelta(seconds=10), fixed_delay=None, initial_delay=timedelta(0))

    assert start_times(every_ten_seconds, [25.0, 1.0, 1.0, 1.0]) == [0.0, 25.0, 26.0, 30.0]


def test_a_fixed_rate_after_an_initial_delay_keeps_to_the_schedule_of_its_first_run() -> None:
    mapping = ScheduledMapping(fixed_rate=timedelta(seconds=10), fixed_delay=None, initial_delay=timedelta(seconds=5))

    assert start_times(mapping, [1.0, 12.0, 1.0]) == [5.0, 15.0, 27.0]


def test_a_fixed_delay_moves_with_a_long_run() -> None:
    mapping = ScheduledMapping(fixed_rate=None, fixed_delay=timedelta(seconds=10), initial_delay=timedelta(0))

    assert start_times(mapping, [25.0, 1.0]) == [0.0, 35.0]


def test_the_first_run_waits_the_initial_delay() -> None:
    mapping = ScheduledMapping(fixed_rate=SECOND, fixed_delay=None, initial_delay=timedelta(seconds=5))

    assert mapping.first_run(now=100.0) == 105.0
