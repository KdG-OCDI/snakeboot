"""The database in memory of a test lets one thread at a time use its one connection, as a test's server threads,
its scheduler and its listeners all reach it."""

import threading
from collections.abc import Iterator

import pytest
from sqlalchemy import text

from snakeboot.sqlalchemy_data import Database
from snakeboot.sqlalchemy_data.testing import in_memory_database

WAIT_SECONDS = 5


@pytest.fixture
def database() -> Iterator[Database]:
    database = in_memory_database()
    with database.transaction() as session:
        session.execute(text("CREATE TABLE seats (id INTEGER PRIMARY KEY)"))
    yield database
    database.close()


def count(database: Database) -> int:
    with database.session() as session:
        return int(session.execute(text("SELECT COUNT(*) FROM seats")).scalar_one())


def test_a_second_thread_waits_for_the_transaction_of_the_first(database: Database) -> None:
    inside, release = threading.Event(), threading.Event()
    counted: list[int] = []

    def hold_a_transaction() -> None:
        with database.transaction() as session:
            session.execute(text("INSERT INTO seats (id) VALUES (1)"))
            inside.set()
            release.wait(WAIT_SECONDS)

    def count_meanwhile() -> None:
        counted.append(count(database))

    holder = threading.Thread(target=hold_a_transaction)
    holder.start()
    assert inside.wait(WAIT_SECONDS)
    counter = threading.Thread(target=count_meanwhile)
    counter.start()
    counter.join(0.2)
    assert counter.is_alive(), "the second thread used the connection while the first held a transaction"

    release.set()
    holder.join(WAIT_SECONDS)
    counter.join(WAIT_SECONDS)

    assert counted == [1]
