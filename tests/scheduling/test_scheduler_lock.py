"""A `@scheduled` method with a `@scheduler_lock` runs only in the process that takes the lock."""

import threading
from datetime import timedelta
from typing import override

import pytest

from snakeboot.scheduling import (
    HeldLock,
    InvalidScheduledTaskError,
    SchedulerLockMapping,
    SchedulerLockProvider,
    TaskScheduler,
    scheduler_lock,
)
from tests.scheduling.sample_jobs.locked.jobs import HourlyReport
from tests.scheduling.stand_ins import CountingTaskDecorator, ScannedComponents

LOCKED = "tests.scheduling.sample_jobs.locked"
WAIT_SECONDS = 5


class CountingLocks(SchedulerLockProvider):
    """Hands out the lock while `free`, and counts what it was asked."""

    def __init__(self, *, free: bool) -> None:
        self.free = free
        self.asked: list[SchedulerLockMapping] = []
        self.released = 0
        self.asked_twice = threading.Event()

    @override
    def try_lock(self, lock: SchedulerLockMapping) -> HeldLock | None:
        self.asked.append(lock)
        if len(self.asked) >= 2:
            self.asked_twice.set()
        return Released(self) if self.free else None


class Released(HeldLock):
    def __init__(self, provider: CountingLocks) -> None:
        self._provider = provider

    @override
    def release(self) -> None:
        self._provider.released += 1


def started(report: HourlyReport, locks: CountingLocks | None) -> TaskScheduler:
    scheduler = TaskScheduler(
        ScannedComponents(LOCKED, report), CountingTaskDecorator(), auto_startup=True, lock_provider=locks
    )
    scheduler.start()
    return scheduler


def test_the_method_runs_when_the_lock_is_taken_and_lets_it_go_after() -> None:
    report, locks = HourlyReport(), CountingLocks(free=True)
    scheduler = started(report, locks)
    try:
        assert report.ran_twice.wait(WAIT_SECONDS)
    finally:
        scheduler.stop()

    assert locks.asked[0] == SchedulerLockMapping("hourly-report", timedelta(minutes=50), timedelta(minutes=1))
    assert locks.released >= 2


def test_the_method_skips_its_turn_while_another_process_holds_the_lock() -> None:
    report, locks = HourlyReport(), CountingLocks(free=False)
    scheduler = started(report, locks)
    try:
        assert locks.asked_twice.wait(WAIT_SECONDS)
    finally:
        scheduler.stop()

    assert report.traces == []


def test_every_run_is_a_trace_of_its_own() -> None:
    report = HourlyReport()
    scheduler = started(report, CountingLocks(free=True))
    try:
        assert report.ran_twice.wait(WAIT_SECONDS)
    finally:
        scheduler.stop()

    first, second = report.traces[:2]
    assert first is not None
    assert second is not None
    assert first != second


def test_a_locked_method_without_a_lock_provider_stops_the_start() -> None:
    scheduler = TaskScheduler(ScannedComponents(LOCKED, HourlyReport()), CountingTaskDecorator(), auto_startup=True)

    with pytest.raises(InvalidScheduledTaskError, match="has a @scheduler_lock, whose lock lives in the database"):
        scheduler.start()


@pytest.mark.parametrize(
    ("at_most_for", "at_least_for"),
    [
        pytest.param(timedelta(0), timedelta(0), id="not held at all"),
        pytest.param(timedelta(minutes=1), timedelta(minutes=2), id="at least longer than at most"),
        pytest.param(timedelta(minutes=1), timedelta(seconds=-1), id="negative"),
    ],
)
def test_a_lock_held_for_no_sensible_time_is_refused(at_most_for: timedelta, at_least_for: timedelta) -> None:
    with pytest.raises(InvalidScheduledTaskError, match="needs a positive at_most_for"):
        scheduler_lock("report", at_most_for=at_most_for, at_least_for=at_least_for)


def test_a_lock_has_a_name() -> None:
    with pytest.raises(InvalidScheduledTaskError, match="names its lock"):
        scheduler_lock("", at_most_for=timedelta(minutes=1))
