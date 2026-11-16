import inspect
from collections.abc import Callable
from functools import wraps
from typing import overload

from snakeboot.transaction.transaction_definition import Isolation, Propagation, TransactionDefinition
from snakeboot.transaction.transaction_manager_registry import TransactionManagerRegistry


@overload
def transactional[**P, R](operation: Callable[P, R], /) -> Callable[P, R]: ...


@overload
def transactional[**P, R](
    *,
    propagation: Propagation = Propagation.REQUIRED,
    isolation: Isolation = Isolation.DEFAULT,
    read_only: bool = False,
    no_rollback_for: tuple[type[BaseException], ...] = (),
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def transactional[**P, R](
    operation: Callable[P, R] | None = None,
    /,
    *,
    propagation: Propagation = Propagation.REQUIRED,
    isolation: Isolation = Isolation.DEFAULT,
    read_only: bool = False,
    no_rollback_for: tuple[type[BaseException], ...] = (),
) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
    """Declares that `operation` runs in a transaction, like Spring's `@Transactional`.

    Put it on the `execute` method of a use case that changes state. Without a running transaction the call starts
    one, which commits when `operation` returns and rolls back when it raises. Inside a running transaction the call
    joins it (`Propagation.REQUIRED`, the default): one transaction, one commit at the outermost call, and an
    exception that leaves the call marks the whole transaction rollback-only, even when a caller catches it. Choose
    `propagation=Propagation.NESTED` for a savepoint whose failure undoes only the call's own work, or
    `Propagation.REQUIRES_NEW` for an independent transaction. `isolation`, `read_only` and `no_rollback_for` are
    described by `TransactionDefinition`. Which technology opens the transaction is decided by the TransactionManager
    composition installed; a timeout, as Spring's `timeout`, is not offered.

    The decorator wraps the Python method itself, so it also applies when another method of the same object calls it
    through `self`: unlike Spring's default proxies, which a call inside the object passes by.
    """
    definition = TransactionDefinition(propagation, isolation, read_only, no_rollback_for)

    def decorate(declared: Callable[P, R]) -> Callable[P, R]:
        return _transactional(declared, definition)

    return decorate if operation is None else decorate(operation)


def _transactional[**P, R](operation: Callable[P, R], definition: TransactionDefinition) -> Callable[P, R]:
    if inspect.iscoroutinefunction(operation):
        raise TypeError(
            f"{operation.__qualname__} is an async function; @transactional supports synchronous operations only."
        )

    @wraps(operation)
    def run_in_transaction(*args: P.args, **kwargs: P.kwargs) -> R:
        with TransactionManagerRegistry.current().atomic(definition):
            result = operation(*args, **kwargs)
            if inspect.iscoroutine(result):
                result.close()
                raise TypeError(
                    f"{operation.__qualname__} returned a coroutine; "
                    "@transactional supports synchronous operations only."
                )
            return result

    return run_in_transaction
