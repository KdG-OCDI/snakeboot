"""`save_all` is atomic; `save_and_flush` and `flush` write now; `@transactional` on a call through `self`."""

from collections.abc import Iterable, Iterator

import pytest

from snakeboot.data import REPOSITORY_ATTRIBUTE, DataIntegrityViolationError, OptimisticLockingFailureError
from snakeboot.sqlalchemy_data import Database, SqlAlchemyTransactionManager
from snakeboot.sqlalchemy_data.entity_mapping import EntityMapping
from snakeboot.sqlalchemy_data.sqlalchemy_repository_operations import SqlAlchemyRepositoryOperations
from snakeboot.sqlalchemy_data.testing import in_memory_database
from snakeboot.transaction import TransactionManagerRegistry, UnexpectedRollbackError, transactional
from tests.data.sample_entities import WorkshopRecord, WorkshopRecords
from tests.sqlalchemy_data.test_database import RefusedError, fail_in


@pytest.fixture
def database() -> Iterator[Database]:
    database = in_memory_database()
    mapping = EntityMapping.of([WorkshopRecord])
    mapping.metadata.create_all(database.engine, tables=mapping.tables)
    TransactionManagerRegistry.install(SqlAlchemyTransactionManager(database))
    yield database
    TransactionManagerRegistry.uninstall()
    database.close()


@pytest.fixture
def workshops(database: Database) -> WorkshopRecords:
    operations = SqlAlchemyRepositoryOperations(database, EntityMapping.of([WorkshopRecord]))
    implementation: WorkshopRecords = getattr(WorkshopRecords, REPOSITORY_ATTRIBUTE)(operations)
    return implementation


def titles(workshops: WorkshopRecords) -> dict[str, str]:
    return {workshop.id: workshop.title for workshop in workshops.find_all()}


def broken(identifier: str) -> WorkshopRecord:
    return WorkshopRecord(identifier, None)  # type: ignore[arg-type]


def test_save_all_without_a_transaction_saves_nothing_when_one_entity_fails(workshops: WorkshopRecords) -> None:
    with pytest.raises(DataIntegrityViolationError):
        workshops.save_all([WorkshopRecord("w1", "Clean Code"), broken("w2")])

    assert titles(workshops) == {}


def test_save_all_restores_the_rows_it_updated_before_one_failed(workshops: WorkshopRecords) -> None:
    saved = workshops.save(WorkshopRecord("w1", "Clean Code"))
    saved.title = "Changed"

    with pytest.raises(DataIntegrityViolationError):
        workshops.save_all([saved, broken("w2")])

    assert titles(workshops) == {"w1": "Clean Code"}


def test_save_all_rolls_back_when_reading_its_entities_fails(workshops: WorkshopRecords) -> None:
    def entities() -> Iterable[WorkshopRecord]:
        yield WorkshopRecord("w1", "Clean Code")
        raise RefusedError

    with pytest.raises(RefusedError):
        workshops.save_all(entities())

    assert titles(workshops) == {}


def test_save_all_returns_the_saved_entities_in_order(workshops: WorkshopRecords) -> None:
    saved = workshops.save_all([WorkshopRecord("w2", "Second"), WorkshopRecord("w1", "First")])

    assert [(workshop.id, workshop.version) for workshop in saved] == [("w2", 1), ("w1", 1)]


def test_save_all_of_nothing_changes_nothing(workshops: WorkshopRecords) -> None:
    assert workshops.save_all([]) == []
    assert titles(workshops) == {}


def test_a_failing_save_all_marks_the_running_transaction_rollback_only(
    database: Database, workshops: WorkshopRecords
) -> None:
    def catches_the_failure_of_save_all() -> None:
        with database.transaction():
            workshops.save(WorkshopRecord("w0", "Before"))
            with pytest.raises(DataIntegrityViolationError):
                workshops.save_all([WorkshopRecord("w1", "Clean Code"), broken("w2")])

    with pytest.raises(UnexpectedRollbackError):
        catches_the_failure_of_save_all()

    assert titles(workshops) == {}


def test_a_successful_save_all_rolls_back_with_the_outer_transaction(
    database: Database, workshops: WorkshopRecords
) -> None:
    with pytest.raises(RefusedError):
        fail_in(database.transaction(), lambda: workshops.save_all([WorkshopRecord("w1", "Clean Code")]))

    assert titles(workshops) == {}


def test_save_and_flush_raises_a_broken_constraint_before_the_transaction_ends(
    database: Database, workshops: WorkshopRecords
) -> None:
    reached: list[str] = []

    def saves_a_broken_entity() -> None:
        with database.transaction():
            workshops.save_and_flush(broken("w1"))
            reached.append("after save_and_flush")

    with pytest.raises(DataIntegrityViolationError):
        saves_a_broken_entity()
    assert reached == []


def test_save_and_flush_raises_the_version_at_once_and_a_rollback_still_undoes_it(
    database: Database, workshops: WorkshopRecords
) -> None:
    workshops.save(WorkshopRecord("w1", "Clean Code"))

    versions: list[int | None] = []

    def change() -> None:
        found = workshops.find_by_id("w1")
        assert found is not None
        found.title = "Changed"
        versions.append(workshops.save_and_flush(found).version)

    with pytest.raises(RefusedError):
        fail_in(database.transaction(), change)

    assert versions == [2]

    assert titles(workshops) == {"w1": "Clean Code"}


def test_flush_writes_a_change_the_transaction_found_and_a_lost_update_shows_there(
    database: Database, workshops: WorkshopRecords
) -> None:
    workshops.save(WorkshopRecord("w1", "Clean Code"))

    def change_what_another_changed_meanwhile() -> None:
        with database.transaction() as session:
            found = workshops.find_by_id("w1")
            assert found is not None
            session.connection().exec_driver_sql("UPDATE data_workshop SET version = version + 1")
            found.title = "Changed"
            workshops.flush()

    with pytest.raises(OptimisticLockingFailureError):
        change_what_another_changed_meanwhile()


def test_flush_outside_a_transaction_does_nothing(workshops: WorkshopRecords) -> None:
    workshops.flush()

    assert titles(workshops) == {}


class Catalogue:
    """A service whose public method is not transactional, and calls a transactional one through `self`."""

    def __init__(self, workshops: WorkshopRecords) -> None:
        self._workshops = workshops
        self.inside_a_transaction: list[bool] = []

    def publish(self, *titles: str) -> None:
        self._add_all(titles)

    @transactional
    def _add_all(self, titles: Iterable[str]) -> None:
        self.inside_a_transaction.append(TransactionManagerRegistry.current().in_transaction)
        for title in titles:
            self._workshops.save(WorkshopRecord(title.lower().replace(" ", "-"), title))
            if title == "refused":
                raise RefusedError


def test_a_transactional_method_called_through_self_runs_in_a_transaction(workshops: WorkshopRecords) -> None:
    catalogue = Catalogue(workshops)

    catalogue.publish("Clean Code")
    with pytest.raises(RefusedError):
        catalogue.publish("Clean Architecture", "refused")

    assert catalogue.inside_a_transaction == [True, True]
    assert titles(workshops) == {"clean-code": "Clean Code"}
