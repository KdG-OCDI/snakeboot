from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Final

from snakeboot.transaction.transaction_definition import TransactionDefinition, TransactionPhase
from snakeboot.transaction.transaction_synchronizations import run_robustly

DEFAULT_DEFINITION: Final = TransactionDefinition()
"""`Propagation.REQUIRED`, the database's isolation, read-write, and a rollback on every exception."""


class TransactionManager(ABC):
    """Opens a transaction in a concrete technology, like Spring's PlatformTransactionManager.

    `@transactional` and `after_commit` only know this abstraction. Composition installs
    the concrete manager (SQLAlchemy's transactions in production, a recording fake in tests), so
    use cases declare transaction behaviour without depending on the persistence technology.

    A manager follows the `Propagation` of each call: it joins the running transaction (`REQUIRED`), opens a savepoint
    in it (`NESTED`) or suspends it for an independent one (`REQUIRES_NEW`). An exception that leaves a joined call
    marks the transaction rollback-only; the outermost call then rolls back and raises `UnexpectedRollbackError`.
    """

    @abstractmethod
    def atomic(self, definition: TransactionDefinition = DEFAULT_DEFINITION) -> AbstractContextManager[None]:
        """Returns a context manager that runs its block in a transaction as `definition` asks.

        A transaction it starts commits when the block ends and rolls back when the block raises an exception that
        `definition` rolls back on.
        """

    @property
    @abstractmethod
    def in_transaction(self) -> bool:
        """Tells whether a transaction runs in this context (this thread, this task) right now."""

    @abstractmethod
    def register(self, phase: TransactionPhase, callback: Callable[[], None]) -> None:
        """Runs `callback` in `phase` of the running transaction; dropped when the savepoint around it rolls back.

        Raises `IllegalTransactionStateError` outside a transaction: there is no commit to wait for.
        """

    def on_commit(self, callback: Callable[[], None]) -> None:
        """Runs `callback` once the current transaction has committed; drops it on a rollback.

        Outside a transaction the callback runs immediately. Callbacks run robustly:
        an exception in one callback is logged, does not prevent others from running and does not
        reach the caller, whose transaction already committed.
        """
        if self.in_transaction:
            self.register(TransactionPhase.AFTER_COMMIT, callback)
        else:
            run_robustly(callback)
