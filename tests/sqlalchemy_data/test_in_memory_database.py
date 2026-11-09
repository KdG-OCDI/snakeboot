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


def test_threads_that_take_turns_many_times_leave_the_connection_free(database: Database) -> None:
    # A background thread (a scheduler, a listener) and a test's thread use the database again and again: every turn
    # gives the connection back, so neither ever waits for one the other no longer uses.
    stop, background_counts, failures = threading.Event(), [0], list[BaseException]()

    def background_work() -> None:
        try:
            while not stop.is_set():
                count(database)
                background_counts[0] += 1
        except BaseException as error:  # noqa: BLE001  # reason: the test reports what the thread met
            failures.append(error)

    worker = threading.Thread(target=background_work)
    worker.start()
    try:
        counts = [count(database) for _ in range(200)]
    finally:
        stop.set()
        worker.join(WAIT_SECONDS)

    assert counts == [0] * 200
    assert not worker.is_alive(), "the background thread still waits for the connection"
    assert (failures, background_counts[0] > 0) == ([], True)


def test_a_thread_that_waited_for_the_connection_gives_it_back(database: Database) -> None:
    # The order in which SQLAlchemy's pool of one connection lost track: one thread holds the connection, a second asks
    # for it meanwhile and gets it once the first gives it back. When the second is done, the first gets it again.
    asked, counted = threading.Event(), list[int]()

    def ask_meanwhile() -> None:
        asked.set()
        counted.append(count(database))

    second = threading.Thread(target=ask_meanwhile)
    with database.transaction() as session:
        session.execute(text("INSERT INTO seats (id) VALUES (1)"))
        second.start()
        asked.wait(WAIT_SECONDS)
        threading.Event().wait(0.2)  # the second thread now asks for the connection the first holds
    second.join(WAIT_SECONDS)

    assert (counted, count(database)) == ([1], 1)
