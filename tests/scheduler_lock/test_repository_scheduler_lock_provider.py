"""In the database, one process at a time holds a scheduler lock, until it lets go or its time is up."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from snakeboot.data import REPOSITORY_ATTRIBUTE
from snakeboot.scheduler_lock import RepositorySchedulerLockProvider, SchedulerLockRecord, SchedulerLockRecords
from snakeboot.scheduling import SchedulerLockMapping
from snakeboot.sqlalchemy_data import Database
from snakeboot.sqlalchemy_data.entity_mapping import EntityMapping
from snakeboot.sqlalchemy_data.sqlalchemy_repository_operations import SqlAlchemyRepositoryOperations
from snakeboot.sqlalchemy_data.testing import in_memory_database

REPORT = SchedulerLockMapping("hourly-report", at_most_for=timedelta(minutes=50), at_least_for=timedelta(minutes=5))
NINE = datetime(2026, 11, 9, 9, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = NINE

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def records() -> Iterator[SchedulerLockRecords]:
    database: Database = in_memory_database()
    mapping = EntityMapping.of([SchedulerLockRecord])
    mapping.metadata.create_all(database.engine, tables=mapping.tables)
    repository: SchedulerLockRecords = getattr(SchedulerLockRecords, REPOSITORY_ATTRIBUTE)(
        SqlAlchemyRepositoryOperations(database, mapping)
    )
    yield repository
    database.close()


@pytest.fixture
def clock() -> Clock:
    return Clock()


def process(records: SchedulerLockRecords, clock: Clock, name: str) -> RepositorySchedulerLockProvider:
    # Two providers in one test stand for two processes.
    return RepositorySchedulerLockProvider(records, clock, holder=name)


def test_the_first_process_takes_the_lock_and_another_is_refused(records: SchedulerLockRecords, clock: Clock) -> None:
    first, second = process(records, clock, "web-1"), process(records, clock, "web-2")

    assert first.try_lock(REPORT) is not None
    assert second.try_lock(REPORT) is None

    lock = records.find_by_id("hourly-report")
    assert lock is not None
    assert (lock.locked_by, lock.locked_at, lock.lock_until) == ("web-1", NINE, NINE + timedelta(minutes=50))


def test_a_lock_let_go_after_a_short_run_stays_held_at_least_for_its_minimum(
    records: SchedulerLockRecords, clock: Clock
) -> None:
    first, second = process(records, clock, "web-1"), process(records, clock, "web-2")
    held = first.try_lock(REPORT)
    assert held is not None
    clock.now = NINE + timedelta(seconds=10)

    held.release()

    assert second.try_lock(REPORT) is None
    clock.now = NINE + timedelta(minutes=5)
    assert second.try_lock(REPORT) is not None


def test_a_lock_let_go_after_a_long_run_is_free_at_once(records: SchedulerLockRecords, clock: Clock) -> None:
    first, second = process(records, clock, "web-1"), process(records, clock, "web-2")
    held = first.try_lock(REPORT)
    assert held is not None
    clock.now = NINE + timedelta(minutes=20)

    held.release()

    assert second.try_lock(REPORT) is not None


def test_the_lock_of_a_process_that_died_is_free_once_its_time_is_up(
    records: SchedulerLockRecords, clock: Clock
) -> None:
    first, second = process(records, clock, "web-1"), process(records, clock, "web-2")
    assert first.try_lock(REPORT) is not None

    clock.now = NINE + timedelta(minutes=49)
    assert second.try_lock(REPORT) is None
    clock.now = NINE + timedelta(minutes=50)
    assert second.try_lock(REPORT) is not None


def test_a_late_release_does_not_free_the_lock_another_process_took_meanwhile(
    records: SchedulerLockRecords, clock: Clock
) -> None:
    first, second = process(records, clock, "web-1"), process(records, clock, "web-2")
    late = first.try_lock(REPORT)
    assert late is not None
    clock.now = NINE + timedelta(minutes=51)
    assert second.try_lock(REPORT) is not None

    late.release()

    lock = records.find_by_id("hourly-report")
    assert lock is not None
    assert (lock.locked_by, lock.lock_until) == ("web-2", NINE + timedelta(minutes=101))
