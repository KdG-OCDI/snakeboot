import threading
from typing import Any, Final, override

from sqlalchemy import StaticPool, create_engine
from sqlalchemy.pool import ConnectionPoolEntry

from snakeboot.sqlalchemy_data.database import Database
from snakeboot.sqlalchemy_data.postgresql_container import ContainerUnavailableError, postgresql_database
from snakeboot.sqlalchemy_data.sqlite import SQLITE_DATETIME, open_transactions_with_sqlalchemy

__all__ = [
    "HOLD_SECONDS",
    "SQLITE_DATETIME",
    "ContainerUnavailableError",
    "OneThreadAtATimePool",
    "in_memory_database",
    "postgresql_database",
]

HOLD_SECONDS: Final = 10
"""How long a thread waits for the connection another holds, before the test fails instead of hanging."""


class OneThreadAtATimePool(StaticPool):
    """SQLAlchemy's pool of one connection, lent to one thread at a time.

    Every thread of a test shares the one connection of an SQLite in memory, so a test's server threads see what the
    test wrote. Lent to two threads at once, the second would begin a transaction inside the first's. The lock is
    taken before the pool hands out its connection, and given back with it: a thread that waits touches nothing of
    the connection another holds. Reentrant, so a thread that holds it may take it once more.
    """

    def __init__(self, *arguments: Any, **options: Any) -> None:
        super().__init__(*arguments, **options)
        self._holder = threading.RLock()

    @override
    def _do_get(self) -> ConnectionPoolEntry:
        if not self._holder.acquire(timeout=HOLD_SECONDS):
            raise TimeoutError(
                f"Another thread held the database in memory for {HOLD_SECONDS} seconds: does a test wait, inside a "
                "transaction, for a call to the API or for a background thread?"
            )
        return super()._do_get()

    @override
    def _do_return_conn(self, record: ConnectionPoolEntry) -> None:
        super()._do_return_conn(record)
        self._holder.release()


def in_memory_database() -> Database:
    """Returns a fresh SQLite database in memory, with savepoints and foreign keys, for tests.

    Every thread shares its one connection, so a test's server threads see what the test wrote, and one thread at a
    time holds it (`OneThreadAtATimePool`): the test, a call to the API, the scheduler, a listener or the event
    publication registry never begin a transaction inside another's. SQLAlchemy opens its transactions, with
    savepoints and foreign keys, as for a file of `[database]` (`open_transactions_with_sqlalchemy`).
    """
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=OneThreadAtATimePool)
    open_transactions_with_sqlalchemy(engine, begin="BEGIN")
    return Database(engine)
