from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import override

from snakeboot.transaction import TransactionManager


class RecordingTransactionManager(TransactionManager):
    """Test double: remembers which transactions were opened, committed and rolled back.

    Application tests install it to run `@transactional` use cases without a database,
    to assert that a use case really runs inside a transaction, and to check that
    `after_commit` callbacks run only after a commit.
    """

    def __init__(self) -> None:
        self.opened = 0
        self.committed = 0
        self.rolled_back = 0
        self._depth = 0
        self._pending_callbacks: list[Callable[[], None]] = []
        self.callback_errors: list[Exception] = []

    @property
    def in_transaction(self) -> bool:
        """Tells whether a transaction is open right now, so a test can check where code runs."""
        return self._depth > 0

    @override
    def atomic(self) -> AbstractContextManager[None]:
        return self._record_transaction()

    @override
    def on_commit(self, callback: Callable[[], None]) -> None:
        if self.in_transaction:
            self._pending_callbacks.append(callback)
        else:
            self._execute_robustly(callback)

    def _execute_robustly(self, callback: Callable[[], None]) -> None:
        try:
            callback()
        except Exception as error:  # noqa: BLE001 - like Django's robust on_commit, any callback error is recorded
            self.callback_errors.append(error)

    @contextmanager
    def _record_transaction(self) -> Iterator[None]:
        self.opened += 1
        self._depth += 1
        try:
            yield
        except BaseException:
            self._depth -= 1
            self.rolled_back += 1
            self._pending_callbacks.clear()
            raise
        self._depth -= 1
        self.committed += 1
        if not self.in_transaction:
            callbacks, self._pending_callbacks = self._pending_callbacks, []
            for callback in callbacks:
                self._execute_robustly(callback)
