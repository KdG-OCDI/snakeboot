"""On PostgreSQL: the scheduler locks, the event publication registry, the stream offsets and optimistic locking.

Set SNAKEBOOT_TEST_POSTGRESQL_URL as for `test_postgresql.py`.
"""

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import create_engine, text

from snakeboot.data import REPOSITORY_ATTRIBUTE, OptimisticLockingFailureError, PageRequest
from snakeboot.event_publication import (
    EventPublicationRecord,
    EventPublicationRecords,
    PersistentEventPublicationRegistry,
    RepositoryStreamOffsets,
    StreamOffsetRecord,
    StreamOffsetRecords,
)
from snakeboot.events import StreamEvent, StreamPosition
from snakeboot.scheduler_lock import RepositorySchedulerLockProvider, SchedulerLockRecord, SchedulerLockRecords
from snakeboot.scheduling import SchedulerLockMapping
from snakeboot.sqlalchemy_data import Database, SqlAlchemyTransactionManager
from snakeboot.sqlalchemy_data.entity_mapping import EntityMapping
from snakeboot.sqlalchemy_data.sqlalchemy_repository_operations import SqlAlchemyRepositoryOperations
from snakeboot.transaction import TransactionManagerRegistry
from tests.data.sample_entities import WorkshopRecord, WorkshopRecords

URL = os.environ.get("SNAKEBOOT_TEST_POSTGRESQL_URL", "")

pytestmark = pytest.mark.skipif(not URL, reason="SNAKEBOOT_TEST_POSTGRESQL_URL names no PostgreSQL")

ENTITIES = (EventPublicationRecord, SchedulerLockRecord, StreamOffsetRecord, WorkshopRecord)


@dataclass(frozen=True)
class ShipmentSent:
    shipment_id: UUID
    sent_at: datetime


def opened() -> Database:
    # A lock that is waited for instead of skipped fails the test after two seconds instead of hanging it.
    return Database(create_engine(URL, connect_args={"options": "-c lock_timeout=2000"}))


@pytest.fixture
def database() -> Iterator[Database]:
    database = opened()
    mapping = EntityMapping.of(ENTITIES)
    with database.engine.begin() as connection:
        for table in mapping.tables:
            connection.execute(text(f"DROP TABLE IF EXISTS {table.name}"))
    mapping.metadata.create_all(database.engine, tables=mapping.tables)
    TransactionManagerRegistry.install(SqlAlchemyTransactionManager(database))
    yield database
    TransactionManagerRegistry.uninstall()
    database.close()


def repository[R](interface: Callable[..., R], database: Database) -> R:
    operations = SqlAlchemyRepositoryOperations(database, EntityMapping.of(ENTITIES))
    implementation: R = getattr(interface, REPOSITORY_ATTRIBUTE)(operations)
    return implementation


def test_one_process_takes_a_scheduler_lock_and_lets_it_go(database: Database) -> None:
    records = repository(SchedulerLockRecords, database)
    lock = SchedulerLockMapping("report", at_most_for=timedelta(minutes=10), at_least_for=timedelta(0))
    first = RepositorySchedulerLockProvider(records, holder="web-1")
    second = RepositorySchedulerLockProvider(records, holder="web-2")

    held = first.try_lock(lock)
    assert held is not None
    assert second.try_lock(lock) is None
    held.release()

    assert second.try_lock(lock) is not None


def test_a_claimed_publication_is_skipped_by_another_process_instead_of_waited_for(database: Database) -> None:
    other = opened()
    registry = PersistentEventPublicationRegistry(repository(EventPublicationRecords, database))
    registry.store(ShipmentSent(UUID(int=7), datetime(2026, 11, 9, tzinfo=UTC)), ["myapp.Listener.on_sent"])
    now = datetime.now(UTC) + timedelta(hours=1)
    mine, theirs = repository(EventPublicationRecords, database), repository(EventPublicationRecords, other)
    try:
        with database.transaction():
            locked = mine.find_by_due_at_less_than_equal_and_attempts_less_than_order_by_due_at_asc(
                now, 10, PageRequest(0, 10)
            )
            skipped = theirs.find_by_due_at_less_than_equal_and_attempts_less_than_order_by_due_at_asc(
                now, 10, PageRequest(0, 10)
            )
    finally:
        other.close()

    assert (len(locked), skipped) == (1, [])


def test_a_publication_keeps_its_event_as_jsonb_and_reads_it_back(database: Database) -> None:
    records = repository(EventPublicationRecords, database)
    clock = [datetime(2026, 11, 9, 9, tzinfo=UTC)]
    registry = PersistentEventPublicationRegistry(records, clock=lambda: clock[0])
    sent = ShipmentSent(UUID(int=7), datetime(2026, 11, 9, 8, tzinfo=UTC))
    [stored] = registry.store(sent, ["myapp.Listener.on_sent"])
    registry.fail(stored, RuntimeError("down"))
    clock[0] += timedelta(hours=1)

    [claimed] = registry.claim_due()

    assert claimed.event == sent
    with database.engine.connect() as connection:
        kind = connection.execute(
            text("SELECT jsonb_typeof(event) FROM snakeboot_event_publication WHERE publication_id = :id"),
            {"id": stored.identifier},
        ).scalar_one()
    assert kind == "object"


def test_a_stream_offset_commits_and_rolls_back_with_the_projection(database: Database) -> None:
    offsets = RepositoryStreamOffsets(repository(StreamOffsetRecords, database))
    workshops = repository(WorkshopRecords, database)

    def project(workshop_id: str, offset: int, *, fails: bool = False) -> bool:
        with database.transaction(), offsets.claiming("myapp.Projection.on_event", StreamEvent(offset)) as new:
            if new:
                workshops.save(WorkshopRecord(workshop_id, "Clean Code"))
            if fails:
                raise RuntimeError("The projection fails.")
            return new

    assert project("w1", 2**40)
    with pytest.raises(RuntimeError):
        project("w2", 2**40 + 1, fails=True)

    assert offsets.last_handled("myapp.Projection.on_event") == 2**40
    assert [workshop.id for workshop in workshops.find_all()] == ["w1"]
    assert offsets.last_handled("myapp.Other.on_event") is None


def test_an_offset_another_process_claimed_is_not_handled_again(database: Database) -> None:
    other = opened()
    mine = RepositoryStreamOffsets(repository(StreamOffsetRecords, database))
    theirs = RepositoryStreamOffsets(repository(StreamOffsetRecords, other))
    try:
        with database.transaction(), mine.claiming("myapp.Projection.on_event", StreamEvent(5)) as first:
            pass
        with other.transaction(), theirs.claiming("myapp.Projection.on_event", StreamEvent(5)) as again:
            pass
        with other.transaction(), theirs.claiming("myapp.Projection.on_event", StreamEvent(4)) as earlier:
            pass
        with other.transaction(), theirs.claiming("myapp.Projection.on_event", StreamEvent(6)) as later:
            pass
    finally:
        other.close()

    assert (first, again, earlier, later) == (True, False, False, True)
    assert mine.last_handled("myapp.Projection.on_event") == 6


def test_of_two_processes_that_find_a_new_stream_one_starts_over_and_a_claim_of_the_old_stream_is_left(
    database: Database,
) -> None:
    other = opened()
    mine = RepositoryStreamOffsets(repository(StreamOffsetRecords, database))
    theirs = RepositoryStreamOffsets(repository(StreamOffsetRecords, other))
    consumer = "myapp.Projection.on_event"
    try:
        with database.transaction(), mine.claiming(consumer, StreamEvent(1000, "old")):
            pass
        seen = mine.position(consumer)
        with database.transaction():
            first = mine.start_over(consumer, seen)
        with other.transaction():
            second = theirs.start_over(consumer, seen)
        with other.transaction(), theirs.claiming(consumer, StreamEvent(1001, "old")) as of_the_old_stream:
            pass
        with database.transaction(), mine.claiming(consumer, StreamEvent(0, "new"), generation=1) as of_the_new:
            pass
    finally:
        other.close()

    assert (seen, first, second) == (StreamPosition(0, StreamEvent(1000, "old")), True, False)
    assert (of_the_old_stream, of_the_new) == (False, True)
    assert mine.position(consumer) == StreamPosition(1, StreamEvent(0, "new"))


def test_saving_a_stale_entity_is_refused(database: Database) -> None:
    workshops = repository(WorkshopRecords, database)
    workshops.save(WorkshopRecord("w1", "Clean Code"))
    ann, bob = workshops.find_by_id("w1"), workshops.find_by_id("w1")
    assert ann is not None
    assert bob is not None
    ann.title = "Ann's"
    workshops.save(ann)
    bob.title = "Bob's"

    with pytest.raises(OptimisticLockingFailureError):
        workshops.save(bob)
