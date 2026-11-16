"""A transaction commits or rolls back; a nested one joins it, or is a savepoint; callbacks wait for the commit."""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from typing import Final

import pytest
from sqlalchemy import text

from snakeboot.sqlalchemy_data import Database, SqlAlchemyTransactionManager
from snakeboot.sqlalchemy_data.entity_mapping import EntityMapping
from snakeboot.sqlalchemy_data.testing import in_memory_database
from snakeboot.transaction import (
    IllegalTransactionStateError,
    Isolation,
    Propagation,
    ReadOnlyTransactionError,
    TransactionDefinition,
    TransactionPhase,
    UnexpectedRollbackError,
)
from tests.data.sample_entities import WorkshopRecord

NESTED: Final = TransactionDefinition(Propagation.NESTED)
BEFORE_COMMIT: Final = TransactionPhase.BEFORE_COMMIT


@pytest.fixture
def database() -> Iterator[Database]:
    database = in_memory_database()
    with database.transaction() as session:
        session.execute(text("CREATE TABLE seats (id INTEGER PRIMARY KEY)"))
    yield database
    database.close()


def seats(database: Database) -> list[int]:
    with database.session() as session:
        return list(session.execute(text("SELECT id FROM seats ORDER BY id")).scalars())


def take(database: Database, seat: int) -> None:
    with database.session() as session:
        session.execute(text("INSERT INTO seats (id) VALUES (:id)"), {"id": seat})


class RefusedError(Exception):
    """Stands in for a use case that fails halfway."""


def fail_in(transaction: AbstractContextManager[object], *work: Callable[[], object]) -> None:
    """Does `work` in `transaction`, then fails, so the transaction rolls back."""
    with transaction:
        for step in work:
            step()
        raise RefusedError


def do_in(transaction: AbstractContextManager[object], *work: Callable[[], object]) -> None:
    """Does `work` in `transaction`."""
    with transaction:
        for step in work:
            step()


def test_a_transaction_commits_when_its_block_ends(database: Database) -> None:
    with database.transaction():
        take(database, 1)

    assert seats(database) == [1]


def test_a_transaction_rolls_back_when_its_block_raises(database: Database) -> None:
    with pytest.raises(RefusedError):
        fail_in(database.transaction(), lambda: take(database, 1))

    assert seats(database) == []


def test_joined_transactions_commit_once_at_the_outermost_end(database: Database) -> None:
    with database.transaction():
        with database.transaction():
            take(database, 1)
        assert database.in_transaction
        with database.transaction():
            take(database, 2)

    assert seats(database) == [1, 2]


def test_a_joined_transaction_that_fails_marks_the_whole_transaction_rollback_only(database: Database) -> None:
    def catches_a_joined_failure() -> None:
        with database.transaction():
            take(database, 1)
            with pytest.raises(RefusedError):
                fail_in(database.transaction(), lambda: take(database, 2))
            take(database, 3)

    with pytest.raises(UnexpectedRollbackError):
        catches_a_joined_failure()

    assert seats(database) == []


def test_the_exception_that_leaves_the_outermost_transaction_stays_visible(database: Database) -> None:
    def joined_failure() -> None:
        fail_in(database.transaction(), lambda: take(database, 2))

    with pytest.raises(RefusedError):
        fail_in(database.transaction(), lambda: take(database, 1), joined_failure)

    assert seats(database) == []


def test_an_exception_caught_inside_a_joined_block_does_not_mark_the_transaction(database: Database) -> None:
    with database.transaction():
        with database.transaction():
            take(database, 1)
            try:
                raise RefusedError
            except RefusedError:
                pass
        take(database, 2)

    assert seats(database) == [1, 2]


def test_a_nested_savepoint_whose_failure_undoes_only_its_own_work(database: Database) -> None:
    with database.transaction():
        take(database, 1)
        with pytest.raises(RefusedError):
            fail_in(database.transaction(NESTED), lambda: take(database, 2))
        take(database, 3)

    assert seats(database) == [1, 3]


def test_a_released_savepoint_still_rolls_back_with_the_outer_transaction(database: Database) -> None:
    def in_a_savepoint() -> None:
        with database.transaction(NESTED):
            take(database, 2)

    with pytest.raises(RefusedError):
        fail_in(database.transaction(), lambda: take(database, 1), in_a_savepoint)

    assert seats(database) == []


def test_a_failure_inside_a_rolled_back_savepoint_does_not_mark_the_outer_transaction(database: Database) -> None:
    def joined_failure_in_a_savepoint() -> None:
        with database.transaction(NESTED):
            fail_in(database.transaction(), lambda: take(database, 2))

    with database.transaction():
        take(database, 1)
        with pytest.raises(RefusedError):
            joined_failure_in_a_savepoint()

    assert seats(database) == [1]


def test_an_exception_named_in_no_rollback_for_commits_and_still_reaches_the_caller(database: Database) -> None:
    lenient = TransactionDefinition(no_rollback_for=(RefusedError,))

    with pytest.raises(RefusedError):
        fail_in(database.transaction(lenient), lambda: take(database, 1))
    with database.transaction():
        with pytest.raises(RefusedError):
            fail_in(database.transaction(lenient), lambda: take(database, 2))
        take(database, 3)

    assert seats(database) == [1, 2, 3]


def test_a_read_only_transaction_refuses_to_write_a_changed_entity(database: Database) -> None:
    mapping = EntityMapping.of([WorkshopRecord])
    mapping.metadata.create_all(database.engine, tables=mapping.tables)
    read_only = TransactionDefinition(read_only=True)
    with database.transaction() as session:
        session.add(WorkshopRecord("w1", "Clean Code"))

    def change_in_a_read_only_transaction() -> None:
        with database.transaction(read_only) as session:
            found = session.get(WorkshopRecord, "w1")
            assert found is not None
            found.title = "Changed"

    with pytest.raises(ReadOnlyTransactionError):
        change_in_a_read_only_transaction()

    with database.transaction(read_only) as session:
        unchanged = session.get(WorkshopRecord, "w1")
        assert unchanged is not None
        assert unchanged.title == "Clean Code"


def test_requires_new_is_refused_on_sqlite(database: Database) -> None:
    requires_new = TransactionDefinition(Propagation.REQUIRES_NEW)

    with database.transaction(), pytest.raises(IllegalTransactionStateError, match="REQUIRES_NEW"):
        database.transaction(requires_new).__enter__()
    with database.transaction(requires_new):
        take(database, 1)

    assert seats(database) == [1]


def test_a_joined_call_cannot_ask_an_isolation(database: Database) -> None:
    serializable = TransactionDefinition(isolation=Isolation.SERIALIZABLE)

    with database.transaction(), pytest.raises(IllegalTransactionStateError, match="keeps its isolation"):
        database.transaction(serializable).__enter__()
    with database.transaction(serializable):
        take(database, 1)

    assert seats(database) == [1]


def test_an_isolation_the_database_does_not_offer_is_refused(database: Database) -> None:
    with (
        pytest.raises(IllegalTransactionStateError, match="offers no isolation"),
        database.transaction(TransactionDefinition(isolation=Isolation.REPEATABLE_READ)),
    ):
        pass


def test_work_outside_a_transaction_runs_in_one_of_its_own(database: Database) -> None:
    take(database, 7)

    assert seats(database) == [7]
    assert not database.in_transaction


def test_a_callback_waits_for_the_outermost_commit(database: Database) -> None:
    manager = SqlAlchemyTransactionManager(database)
    heard: list[str] = []
    with database.transaction():
        with database.transaction(NESTED):
            manager.on_commit(lambda: heard.append("committed"))
        assert heard == []

    assert heard == ["committed"]


def test_a_rollback_drops_the_waiting_callbacks(database: Database) -> None:
    manager = SqlAlchemyTransactionManager(database)
    heard: list[str] = []
    with pytest.raises(RefusedError):
        fail_in(database.transaction(), lambda: manager.on_commit(lambda: heard.append("committed")))

    assert heard == []


def test_a_rolled_back_savepoint_drops_only_its_own_callbacks(database: Database) -> None:
    manager = SqlAlchemyTransactionManager(database)
    heard: list[str] = []
    with database.transaction():
        manager.on_commit(lambda: heard.append("outer"))
        with pytest.raises(RefusedError):
            fail_in(database.transaction(NESTED), lambda: manager.on_commit(lambda: heard.append("inner")))

    assert heard == ["outer"]


def test_outside_a_transaction_a_callback_runs_at_once(database: Database) -> None:
    heard: list[str] = []

    SqlAlchemyTransactionManager(database).on_commit(lambda: heard.append("now"))

    assert heard == ["now"]


def test_a_failing_callback_neither_hides_the_commit_nor_stops_the_others(database: Database) -> None:
    manager = SqlAlchemyTransactionManager(database)
    heard: list[str] = []

    def fail() -> None:
        raise RefusedError

    with database.transaction():
        take(database, 1)
        manager.on_commit(fail)
        manager.on_commit(lambda: heard.append("second"))

    assert (seats(database), heard) == ([1], ["second"])


def test_a_callback_writes_in_a_transaction_of_its_own(database: Database) -> None:
    with database.transaction():
        take(database, 1)
        SqlAlchemyTransactionManager(database).on_commit(lambda: take(database, 2))

    assert seats(database) == [1, 2]
    assert not database.in_transaction


def test_the_callbacks_of_each_phase_run_when_their_phase_comes(database: Database) -> None:
    heard: list[str] = []

    def hear(phase: TransactionPhase, outcome: str) -> Callable[[], None]:
        return lambda: heard.append(f"{phase}: {outcome}")

    for phase in TransactionPhase:
        with database.transaction():
            database.register(phase, hear(phase, "committed"))
        rolled_back = hear(phase, "rolled back")
        with pytest.raises(RefusedError):
            fail_in(database.transaction(), lambda: database.register(phase, rolled_back))  # noqa: B023  # reason: runs at once

    assert heard == [
        "before_commit: committed",
        "after_commit: committed",
        "after_rollback: rolled back",
        "after_completion: committed",
        "after_completion: rolled back",
    ]


def test_a_failing_before_commit_callback_rolls_the_transaction_back(database: Database) -> None:
    def refuse() -> None:
        raise RefusedError

    with pytest.raises(RefusedError):
        do_in(database.transaction(), lambda: take(database, 1), lambda: database.register(BEFORE_COMMIT, refuse))

    assert seats(database) == []


def test_a_before_commit_callback_writes_in_the_transaction(database: Database) -> None:
    with database.transaction():
        database.register(TransactionPhase.BEFORE_COMMIT, lambda: take(database, 5))

    assert seats(database) == [5]


def test_registering_outside_a_transaction_is_refused(database: Database) -> None:
    with pytest.raises(IllegalTransactionStateError, match="No transaction runs"):
        database.register(TransactionPhase.AFTER_COMMIT, lambda: None)


def test_the_transaction_manager_runs_transactional_on_the_database(database: Database) -> None:
    manager = SqlAlchemyTransactionManager(database)

    with pytest.raises(RefusedError):
        fail_in(manager.atomic(), lambda: take(database, 1))
    with manager.atomic():
        take(database, 2)

    assert seats(database) == [2]
