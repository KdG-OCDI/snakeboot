"""A transaction commits or rolls back; a nested one is a savepoint; callbacks wait for the outermost commit."""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager

import pytest
from sqlalchemy import text

from snakeboot.sqlalchemy_data import Database, SqlAlchemyTransactionManager
from snakeboot.sqlalchemy_data.testing import in_memory_database


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


def test_a_transaction_commits_when_its_block_ends(database: Database) -> None:
    with database.transaction():
        take(database, 1)

    assert seats(database) == [1]


def test_a_transaction_rolls_back_when_its_block_raises(database: Database) -> None:
    with pytest.raises(RefusedError):
        fail_in(database.transaction(), lambda: take(database, 1))

    assert seats(database) == []


def test_a_nested_transaction_is_a_savepoint_whose_failure_undoes_only_its_own_work(database: Database) -> None:
    with database.transaction():
        take(database, 1)
        with pytest.raises(RefusedError):
            fail_in(database.transaction(), lambda: take(database, 2))
        take(database, 3)

    assert seats(database) == [1, 3]


def test_work_outside_a_transaction_runs_in_one_of_its_own(database: Database) -> None:
    take(database, 7)

    assert seats(database) == [7]
    assert not database.in_transaction


def test_a_callback_waits_for_the_outermost_commit(database: Database) -> None:
    heard: list[str] = []
    with database.transaction():
        with database.transaction():
            database.on_commit(lambda: heard.append("committed"))
        assert heard == []

    assert heard == ["committed"]


def test_a_rollback_drops_the_waiting_callbacks(database: Database) -> None:
    heard: list[str] = []
    with pytest.raises(RefusedError):
        fail_in(database.transaction(), lambda: database.on_commit(lambda: heard.append("committed")))

    assert heard == []


def test_a_rolled_back_savepoint_drops_only_its_own_callbacks(database: Database) -> None:
    heard: list[str] = []
    with database.transaction():
        database.on_commit(lambda: heard.append("outer"))
        with pytest.raises(RefusedError):
            fail_in(database.transaction(), lambda: database.on_commit(lambda: heard.append("inner")))

    assert heard == ["outer"]


def test_outside_a_transaction_a_callback_runs_at_once(database: Database) -> None:
    heard: list[str] = []

    database.on_commit(lambda: heard.append("now"))

    assert heard == ["now"]


def test_a_failing_callback_neither_hides_the_commit_nor_stops_the_others(database: Database) -> None:
    heard: list[str] = []

    def fail() -> None:
        raise RefusedError

    with database.transaction():
        take(database, 1)
        database.on_commit(fail)
        database.on_commit(lambda: heard.append("second"))

    assert (seats(database), heard) == ([1], ["second"])


def test_the_transaction_manager_runs_transactional_on_the_database(database: Database) -> None:
    manager = SqlAlchemyTransactionManager(database)

    with pytest.raises(RefusedError):
        fail_in(manager.atomic(), lambda: take(database, 1))
    with manager.atomic():
        take(database, 2)

    assert seats(database) == [2]
