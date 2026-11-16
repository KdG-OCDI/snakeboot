from collections.abc import Callable, Generator, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import override

from snakeboot.transaction import (
    DEFAULT_DEFINITION,
    IllegalTransactionStateError,
    Propagation,
    TransactionDefinition,
    TransactionManager,
    TransactionPhase,
    TransactionSynchronizations,
    UnexpectedRollbackError,
)


class RecordingTransactionManager(TransactionManager):
    """Test double: remembers which transactions were opened, committed and rolled back.

    Application tests install it to run `@transactional` use cases without a database,
    to assert that a use case really runs inside a transaction, and to check that
    `after_commit` callbacks run only after a commit. It follows the propagation of a real manager: a joined call
    counts no transaction of its own and marks the transaction rollback-only when it fails, a `NESTED` call is a
    savepoint, a `REQUIRES_NEW` call a transaction of its own. `opened`, `committed` and `rolled_back` count physical
    transactions; `callback_errors` holds what the callbacks raised.
    """

    def __init__(self) -> None:
        self.opened = 0
        self.committed = 0
        self.rolled_back = 0
        self.callback_errors: list[Exception] = []
        self._running: list[TransactionSynchronizations] = []

    @property
    @override
    def in_transaction(self) -> bool:
        return bool(self._running)

    @override
    def atomic(self, definition: TransactionDefinition = DEFAULT_DEFINITION) -> AbstractContextManager[None]:
        return self._record_transaction(definition)

    @override
    def register(self, phase: TransactionPhase, callback: Callable[[], None]) -> None:
        if not self._running:
            raise IllegalTransactionStateError(f"No transaction runs, so there is no {phase} to wait for.")
        self._running[-1].register(phase, self._recorded(callback))

    @override
    def on_commit(self, callback: Callable[[], None]) -> None:
        if self.in_transaction:
            self.register(TransactionPhase.AFTER_COMMIT, callback)
            return
        try:
            callback()
        except Exception as error:  # noqa: BLE001  # reason: like a robust after-commit callback, any error is recorded
            self.callback_errors.append(error)

    def _recorded(self, callback: Callable[[], None]) -> Callable[[], None]:
        def run() -> None:
            try:
                callback()
            except Exception as error:
                self.callback_errors.append(error)
                raise

        return run

    @contextmanager
    def _record_transaction(self, definition: TransactionDefinition) -> Iterator[None]:
        if not self._running or definition.propagation is Propagation.REQUIRES_NEW:
            yield from self._physical(definition)
        elif definition.propagation is Propagation.NESTED:
            yield from self._savepoint(definition)
        else:
            yield from self._joined(definition)

    def _physical(self, definition: TransactionDefinition) -> Generator[None]:
        synchronizations = TransactionSynchronizations()
        self.opened += 1
        self._running.append(synchronizations)
        try:
            surviving = yield from _guarded(definition)
            synchronizations.before_commit()
            if synchronizations.rollback_only:
                raise UnexpectedRollbackError("A @transactional call that joined the transaction failed.")
        except BaseException:
            self._running.pop()
            self.rolled_back += 1
            synchronizations.after_completion(committed=False)
            raise
        self._running.pop()
        self.committed += 1
        synchronizations.after_completion(committed=True)
        if surviving is not None:
            raise surviving

    def _savepoint(self, definition: TransactionDefinition) -> Generator[None]:
        synchronizations = self._running[-1]
        synchronizations.begin_savepoint()
        try:
            surviving = yield from _guarded(definition)
        except BaseException:
            synchronizations.rollback_savepoint()
            raise
        synchronizations.release_savepoint()
        if surviving is not None:
            raise surviving

    def _joined(self, definition: TransactionDefinition) -> Generator[None]:
        try:
            yield
        except BaseException as error:
            if definition.rolls_back_on(error):
                self._running[-1].rollback_only = True
            raise


def _guarded(definition: TransactionDefinition) -> Generator[None, None, BaseException | None]:
    try:
        yield
    except BaseException as error:
        if definition.rolls_back_on(error):
            raise
        return error
    return None
