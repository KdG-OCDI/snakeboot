import inspect
from collections.abc import Callable
from functools import wraps

from snakeboot.transaction.transaction_manager_registry import TransactionManagerRegistry


def transactional[**P, R](operation: Callable[P, R]) -> Callable[P, R]:
    """Declares that `operation` runs in one transaction, like Spring's `@Transactional`.

    Put it on the `execute` method of a use case that changes state. The transaction
    commits when `operation` returns and rolls back when it raises. Which technology
    opens the transaction is decided by the TransactionManager composition installed.
    """
    if inspect.iscoroutinefunction(operation):
        raise TypeError(
            f"{operation.__qualname__} is an async function; @transactional supports synchronous operations only."
        )

    @wraps(operation)
    def run_in_transaction(*args: P.args, **kwargs: P.kwargs) -> R:
        with TransactionManagerRegistry.current().atomic():
            result = operation(*args, **kwargs)
            if inspect.iscoroutine(result):
                result.close()
                raise TypeError(
                    f"{operation.__qualname__} returned a coroutine; "
                    "@transactional supports synchronous operations only."
                )
            return result

    return run_in_transaction
