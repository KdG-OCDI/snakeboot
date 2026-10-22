from collections.abc import Callable

from snakeboot.transaction.transaction_manager_registry import TransactionManagerRegistry


def after_commit(callback: Callable[[], None]) -> None:
    """Defers a side effect until the surrounding `@transactional` operation has committed.

    Use it for effects outside the database, such as notifications: a participant must
    never hear about a seat that a rolled-back transaction took away again. Mirrors
    Spring's `@TransactionalEventListener(phase = AFTER_COMMIT)`.
    """
    TransactionManagerRegistry.current().on_commit(callback)
