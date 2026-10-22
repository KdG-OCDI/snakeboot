from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import override

from django.db import transaction

from snakeboot.transaction import TransactionManager


class DjangoAtomicTransactionManager(TransactionManager):
    """Opens transactions with Django's `transaction.atomic`, for the default database.

    It lives in composition because choosing the transaction technology is a wiring
    decision: the transaction library stays free of Django, and no bounded context
    owns the database connection. Nested `@transactional` calls become savepoints.
    """

    @override
    def atomic(self) -> AbstractContextManager[None]:
        return transaction.atomic()

    @override
    def on_commit(self, callback: Callable[[], None]) -> None:
        transaction.on_commit(callback, robust=True)
