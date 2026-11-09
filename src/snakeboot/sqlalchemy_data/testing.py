import sqlite3
import threading
from datetime import UTC, date, datetime
from typing import Any, Final

from sqlalchemy import Engine, StaticPool, create_engine, event

from snakeboot.sqlalchemy_data.database import Database

SQLITE_DATETIME: Final = "%Y-%m-%d %H:%M:%S.%f"
"""How SQLAlchemy writes a `datetime` column in SQLite: a `@query`'s parameter is written alike, so they compare."""

HOLD_SECONDS: Final = 10
"""How long a thread waits for the connection another holds, before the test fails instead of hanging."""


def in_memory_database() -> Database:
    """Returns a fresh SQLite database in memory, with savepoints and foreign keys, for tests.

    Every thread shares its one connection, so a test's server threads see what the test wrote. One thread at a time
    holds it, from the moment it takes it until it gives it back, as each would hold a connection of its own: the
    test, a call to the API, the scheduler, a listener or the event publication registry never begin a transaction
    inside another's. Python's sqlite3 opens transactions its own way, which breaks savepoints; SQLAlchemy opens them
    here instead, as its documentation advises. A date or a time passed to a `@query` is written as SQLAlchemy writes
    its columns, in UTC, instead of by sqlite3's deprecated default adapters.
    """
    sqlite3.register_adapter(datetime, _sqlite_datetime)
    sqlite3.register_adapter(date, date.isoformat)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    _open_transactions_with_sqlalchemy(engine)
    _one_thread_at_a_time(engine)
    return Database(engine)


def _sqlite_datetime(value: datetime) -> str:
    in_utc = value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo is not None else value
    return in_utc.strftime(SQLITE_DATETIME)


def _open_transactions_with_sqlalchemy(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def connect(connection: Any, _record: object) -> None:
        connection.isolation_level = None
        connection.execute("PRAGMA foreign_keys=ON")

    @event.listens_for(engine, "begin")
    def begin(connection: Any) -> None:
        connection.exec_driver_sql("BEGIN")


def _one_thread_at_a_time(engine: Engine) -> None:
    # The pool hands out its one connection to every thread; the lock makes the others wait until it comes back,
    # instead of beginning a transaction inside the transaction of another thread.
    holder = threading.RLock()

    @event.listens_for(engine, "checkout")
    def checkout(_connection: object, _record: object, _proxy: object) -> None:
        if not holder.acquire(timeout=HOLD_SECONDS):
            raise TimeoutError(
                f"Another thread held the database in memory for {HOLD_SECONDS} seconds: does a test wait, inside a "
                "transaction, for a call to the API or for a background thread?"
            )

    @event.listens_for(engine, "checkin")
    def checkin(_connection: object, _record: object) -> None:
        holder.release()
