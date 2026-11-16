"""On PostgreSQL: `REQUIRES_NEW` runs an independent transaction on a connection of its own; isolation and read-only.

Set SNAKEBOOT_TEST_POSTGRESQL_URL as for `test_postgresql.py`.
"""

import os
from collections.abc import Callable, Iterator
from typing import Final

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from snakeboot.sqlalchemy_data import Database, SqlAlchemyTransactionManager
from snakeboot.transaction import Isolation, Propagation, TransactionDefinition, UnexpectedRollbackError
from tests.sqlalchemy_data.test_database import RefusedError, fail_in

URL = os.environ.get("SNAKEBOOT_TEST_POSTGRESQL_URL", "")

pytestmark = pytest.mark.skipif(not URL, reason="SNAKEBOOT_TEST_POSTGRESQL_URL names no PostgreSQL")

REQUIRES_NEW: Final = TransactionDefinition(Propagation.REQUIRES_NEW)


@pytest.fixture
def database() -> Iterator[Database]:
    database = Database(create_engine(URL))
    with database.transaction() as session:
        session.execute(text("DROP TABLE IF EXISTS pg_seats"))
        session.execute(text("CREATE TABLE pg_seats (id INTEGER PRIMARY KEY)"))
    yield database
    database.close()


def seats(database: Database) -> list[int]:
    with database.session() as session:
        return list(session.execute(text("SELECT id FROM pg_seats ORDER BY id")).scalars())


def take(database: Database, seat: int) -> None:
    with database.session() as session:
        session.execute(text("INSERT INTO pg_seats (id) VALUES (:id)"), {"id": seat})


def independently(database: Database, work: Callable[[], None]) -> None:
    with database.transaction(REQUIRES_NEW):
        work()


def test_an_independent_commit_survives_the_rollback_of_the_outer_transaction(database: Database) -> None:
    with pytest.raises(RefusedError):
        fail_in(
            database.transaction(),
            lambda: take(database, 1),
            lambda: independently(database, lambda: take(database, 2)),
        )

    assert seats(database) == [2]


def test_an_independent_rollback_leaves_the_outer_transaction_able_to_commit(database: Database) -> None:
    def fails() -> None:
        take(database, 2)
        raise RefusedError

    with database.transaction():
        take(database, 1)
        with pytest.raises(RefusedError):
            independently(database, fails)
        assert database.in_transaction
        take(database, 3)

    assert seats(database) == [1, 3]


def test_the_independent_transaction_runs_on_its_own_connection(database: Database) -> None:
    def outer_pid() -> int:
        with database.session() as session:
            return int(session.execute(text("SELECT pg_backend_pid()")).scalar_one())

    with database.transaction():
        outer = outer_pid()
        inner: list[int] = []
        independently(database, lambda: inner.append(outer_pid()))
        assert outer_pid() == outer

    assert inner != [outer]


def test_independent_callbacks_run_after_their_own_commit(database: Database) -> None:
    manager = SqlAlchemyTransactionManager(database)
    heard: list[str] = []

    with database.transaction():
        manager.on_commit(lambda: heard.append("outer"))
        independently(database, lambda: manager.on_commit(lambda: heard.append("inner")))
        assert heard == ["inner"]

    assert heard == ["inner", "outer"]


def test_a_joined_failure_still_rolls_back_everything_on_postgresql(database: Database) -> None:
    def joined_failure() -> None:
        with database.transaction():
            take(database, 2)
            raise RefusedError

    def catches_a_joined_failure() -> None:
        with database.transaction():
            take(database, 1)
            with pytest.raises(RefusedError):
                joined_failure()

    with pytest.raises(UnexpectedRollbackError):
        catches_a_joined_failure()

    assert seats(database) == []


def test_a_transaction_runs_in_the_isolation_it_asks(database: Database) -> None:
    with database.transaction(TransactionDefinition(isolation=Isolation.SERIALIZABLE)) as session:
        level = session.execute(text("SHOW transaction_isolation")).scalar_one()

    assert level == "serializable"


def test_postgresql_refuses_a_native_write_in_a_read_only_transaction(database: Database) -> None:
    with pytest.raises(DBAPIError, match="read-only transaction"):
        fail_in(database.transaction(TransactionDefinition(read_only=True)), lambda: take(database, 1))

    assert seats(database) == []
