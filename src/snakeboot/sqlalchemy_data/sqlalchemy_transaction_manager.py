from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import override

from snakeboot.sqlalchemy_data.database import Database
from snakeboot.transaction import TransactionManager


class SqlAlchemyTransactionManager(TransactionManager):
    """Runs `@transactional` on SQLAlchemy, like Spring's `JpaTransactionManager`.

    The outermost `@transactional` call opens a session and its transaction; a nested one becomes a savepoint, so its
    failure undoes only its own work. `after_commit` waits for the outermost commit and is dropped by a rollback.
    """

    def __init__(self, database: Database) -> None:
        self._database = database

    @override
    def atomic(self) -> AbstractContextManager[None]:
        return self._atomic()

    @override
    def on_commit(self, callback: Callable[[], None]) -> None:
        self._database.on_commit(callback)

    @contextmanager
    def _atomic(self) -> Iterator[None]:
        with self._database.transaction():
            yield
