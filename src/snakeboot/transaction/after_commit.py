from collections.abc import Callable

from snakeboot.transaction.transaction_manager_registry import TransactionManagerRegistry


def after_commit(callback: Callable[[], None]) -> None:
    """Defers a side effect until the surrounding transaction has committed.

    Use it for effects outside the database, such as notifications: a participant must
    never hear about a seat that a rolled-back transaction took away again. Inside a joined
    `@transactional` call it waits for the outermost commit; registered in a `NESTED` savepoint
    that rolls back, it is dropped. Outside a transaction it runs at once.

    The callback runs once the transaction's session is closed and its context cleared: a repository call in it
    runs in a transaction of its own, which commits by itself. A failing callback is logged and the next one still
    runs; its error does not reach the caller, whose work already committed. So a successful transaction does not
    prove that its side effects succeeded: what must happen belongs in an `@application_module_listener`, whose
    publication is kept until it succeeds. Unlike Spring's `TransactionSynchronization.afterCommit`, whose runtime
    exception reaches the caller of the commit.
    """
    TransactionManagerRegistry.current().on_commit(callback)
