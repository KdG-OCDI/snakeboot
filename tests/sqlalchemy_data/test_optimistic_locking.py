"""A `Version()` field guards an entity against lost updates; `CreatedBy()` and `LastModifiedBy()` record who saved."""

import gc
from collections.abc import Iterator

import pytest
from sqlalchemy import text

from snakeboot.data import (
    REPOSITORY_ATTRIBUTE,
    DataIntegrityViolationError,
    OptimisticLockingFailureError,
)
from snakeboot.security import Principal, SecurityContext
from snakeboot.sqlalchemy_data import Database
from snakeboot.sqlalchemy_data.entity_mapping import EntityMapping
from snakeboot.sqlalchemy_data.sqlalchemy_repository_operations import SqlAlchemyRepositoryOperations
from snakeboot.sqlalchemy_data.testing import in_memory_database
from tests.data.sample_entities import MoveRecord, WorkshopRecord, WorkshopRecords


@pytest.fixture
def database() -> Iterator[Database]:
    database = in_memory_database()
    mapping = EntityMapping.of([WorkshopRecord, MoveRecord])
    mapping.metadata.create_all(database.engine, tables=mapping.tables)
    yield database
    database.close()


@pytest.fixture
def workshops(database: Database) -> WorkshopRecords:
    operations = SqlAlchemyRepositoryOperations(database, EntityMapping.of([WorkshopRecord, MoveRecord]))
    implementation: WorkshopRecords = getattr(WorkshopRecords, REPOSITORY_ATTRIBUTE)(operations)
    return implementation


def test_a_new_entity_gets_version_one_and_every_update_raises_it(workshops: WorkshopRecords) -> None:
    saved = workshops.save(WorkshopRecord("w1", "Clean Code"))
    assert saved.version == 1

    saved.title = "Clean Architecture"
    assert workshops.save(saved).version == 2


def test_saving_what_another_saved_meanwhile_is_refused(workshops: WorkshopRecords) -> None:
    workshops.save(WorkshopRecord("w1", "Clean Code"))
    ann, bob = workshops.find_by_id("w1"), workshops.find_by_id("w1")
    assert ann is not None
    assert bob is not None

    ann.title = "Ann's title"
    workshops.save(ann)
    bob.title = "Bob's title"

    with pytest.raises(OptimisticLockingFailureError, match="changed since it was read"):
        workshops.save(bob)
    assert workshops.find_by_id("w1") == WorkshopRecord("w1", "Ann's title", version=2)


def test_deleting_what_another_saved_meanwhile_is_refused(workshops: WorkshopRecords) -> None:
    workshops.save(WorkshopRecord("w1", "Clean Code"))
    stale = workshops.find_by_id("w1")
    fresh = workshops.find_by_id("w1")
    assert stale is not None
    assert fresh is not None
    fresh.title = "Changed"
    workshops.save(fresh)

    with pytest.raises(OptimisticLockingFailureError):
        workshops.delete(stale)
    assert workshops.exists_by_id("w1")


def test_in_a_transaction_an_update_raises_the_version_once(database: Database, workshops: WorkshopRecords) -> None:
    workshops.save(WorkshopRecord("w1", "Clean Code"))
    with database.transaction():
        mine = workshops.find_by_id("w1")
        assert mine is not None
        mine.title = "Mine"
        workshops.save(mine)

    assert workshops.find_by_id("w1") == WorkshopRecord("w1", "Mine", version=2)


def test_a_broken_constraint_is_a_data_integrity_violation(database: Database) -> None:
    operations = SqlAlchemyRepositoryOperations(database, EntityMapping.of([WorkshopRecord, MoveRecord]))
    workshops: WorkshopRecords = getattr(WorkshopRecords, REPOSITORY_ATTRIBUTE)(operations)

    with pytest.raises(DataIntegrityViolationError, match="refused the change"):
        workshops.save(WorkshopRecord("w1", None))  # type: ignore[arg-type]


def test_the_signed_in_principal_creates_and_modifies(workshops: WorkshopRecords) -> None:
    with SecurityContext.signed_in(Principal("olivia")):
        workshops.save(WorkshopRecord("w1", "Clean Code"))
    saved = workshops.find_by_id("w1")
    assert saved is not None

    with SecurityContext.signed_in(Principal("max")):
        saved.title = "Clean Architecture"
        workshops.save(saved)

    assert (saved.created_by, saved.modified_by) == ("olivia", "max")


def test_work_nobody_signed_in_to_leaves_the_auditors_empty(workshops: WorkshopRecords) -> None:
    with SecurityContext.signed_in(Principal("olivia")):
        saved = workshops.save(WorkshopRecord("w1", "Clean Code"))

    saved.title = "Changed by a scheduled job"
    workshops.save(saved)

    assert (saved.created_by, saved.modified_by) == ("olivia", None)


def test_skip_locked_reads_like_a_plain_query_where_nothing_is_locked(workshops: WorkshopRecords) -> None:
    workshops.save(WorkshopRecord("w1", "Clean Code"))

    assert [workshop.id for workshop in workshops.find_by_title("Clean Code")] == ["w1"]


def test_in_a_transaction_the_row_as_read_is_held_although_nobody_holds_its_entity(
    database: Database, workshops: WorkshopRecords
) -> None:
    # The pattern of a hexagonal adapter: read a record, map it to the domain and let it go; save a new record later.
    workshops.save(WorkshopRecord("w1", "Clean Code"))

    def save_after_another_transaction_saved() -> None:
        with database.transaction() as session:
            read = workshops.find_by_id("w1")
            assert read is not None
            title = read.title
            del read
            gc.collect()
            session.execute(text("UPDATE data_workshop SET version = version + 1"))  # another transaction, meanwhile
            held = workshops.find_by_id("w1")
            assert held is not None
            workshops.save(WorkshopRecord("w1", f"{title}, changed", version=held.version))

    with pytest.raises(OptimisticLockingFailureError):
        save_after_another_transaction_saved()
    assert workshops.find_by_id("w1") == WorkshopRecord("w1", "Clean Code", version=1)
