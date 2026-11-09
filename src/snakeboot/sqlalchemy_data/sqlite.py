"""SQLite as snakeboot uses it: a file of `[database] file`, or the database in memory of a test."""

import sqlite3
from datetime import UTC, date, datetime
from typing import Any, Final

from sqlalchemy import Engine, create_engine, event

SQLITE_DATETIME: Final = "%Y-%m-%d %H:%M:%S.%f"
"""How SQLAlchemy writes a `datetime` column in SQLite: a `@query`'s parameter is written alike, so they compare."""

BUSY_SECONDS: Final = 30
"""How long a transaction of a file waits for another one to end before it fails with "database is locked"."""


def sqlite_file_engine(file: str) -> Engine:
    """Returns the engine of the SQLite database in `file`, which every thread of the service shares.

    Each connection runs in WAL mode, so a reader never waits for a writer; a transaction takes the write lock when it
    begins (`BEGIN IMMEDIATE`) and waits up to `BUSY_SECONDS` for another one's, so two transactions never deadlock
    while both try to write. `SELECT ... FOR UPDATE` means nothing in SQLite: the write lock of a transaction is what
    serializes the changes.
    """
    engine = create_engine(f"sqlite:///{file}", connect_args={"check_same_thread": False, "timeout": BUSY_SECONDS})
    open_transactions_with_sqlalchemy(engine, begin="BEGIN IMMEDIATE", journal_mode="WAL")
    return engine


def open_transactions_with_sqlalchemy(engine: Engine, *, begin: str, journal_mode: str | None = None) -> None:
    """Lets SQLAlchemy, not Python's sqlite3, open the transactions of `engine`, with savepoints and foreign keys.

    Python's sqlite3 opens transactions its own way, which breaks savepoints; SQLAlchemy opens them here instead, as
    its documentation advises. A date or a time passed to a `@query` is written as SQLAlchemy writes its columns, in
    UTC, instead of by sqlite3's deprecated default adapters.
    """
    sqlite3.register_adapter(datetime, _sqlite_datetime)
    sqlite3.register_adapter(date, date.isoformat)

    @event.listens_for(engine, "connect")
    def connect(connection: Any, _record: object) -> None:
        connection.isolation_level = None
        connection.execute("PRAGMA foreign_keys=ON")
        if journal_mode is not None:
            connection.execute(f"PRAGMA journal_mode={journal_mode}")

    @event.listens_for(engine, "begin")
    def begin_transaction(connection: Any) -> None:
        connection.exec_driver_sql(begin)


def _sqlite_datetime(value: datetime) -> str:
    in_utc = value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo is not None else value
    return in_utc.strftime(SQLITE_DATETIME)
