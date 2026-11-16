from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import override

from snakeboot.sqlalchemy_data.database import Database
from snakeboot.transaction import DEFAULT_DEFINITION, TransactionDefinition, TransactionManager, TransactionPhase


class SqlAlchemyTransactionManager(TransactionManager):
    """Runs `@transactional` on SQLAlchemy, like Spring's `JpaTransactionManager`.

    The outermost `@transactional` call opens a session and its transaction; a nested one joins it by default, or opens
    a savepoint (`NESTED`) or an independent transaction (`REQUIRES_NEW`), as `Database.transaction` does.
    `after_commit` waits for the commit of the physical transaction and is dropped by a rollback.
    """

    def __init__(self, database: Database) -> None:
        self._database = database

    @override
    def atomic(self, definition: TransactionDefinition = DEFAULT_DEFINITION) -> AbstractContextManager[None]:
        return self._atomic(definition)

    @property
    @override
    def in_transaction(self) -> bool:
        return self._database.in_transaction

    @override
    def register(self, phase: TransactionPhase, callback: Callable[[], None]) -> None:
        self._database.register(phase, callback)

    @contextmanager
    def _atomic(self, definition: TransactionDefinition) -> Iterator[None]:
        with self._database.transaction(definition):
            yield
