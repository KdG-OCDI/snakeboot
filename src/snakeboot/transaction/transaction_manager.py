from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import AbstractContextManager


class TransactionManager(ABC):
    """Opens a transaction in a concrete technology, like Spring's PlatformTransactionManager.

    `@transactional` and `after_commit` only know this abstraction. Composition installs
    the concrete manager (Django's `atomic` in production, a recording fake in tests), so
    use cases declare transaction behaviour without depending on the persistence technology.
    """

    @abstractmethod
    def atomic(self) -> AbstractContextManager[None]:
        """Returns a context manager that commits on success and rolls back on an exception."""

    @abstractmethod
    def on_commit(self, callback: Callable[[], None]) -> None:
        """Runs `callback` once the current transaction has committed; drops it on a rollback.

        Outside a transaction the callback runs immediately. Callbacks run robustly:
        an exception in one callback does not prevent others from running and does not
        mask an already committed transaction.
        """
