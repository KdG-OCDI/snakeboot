import logging
from collections.abc import Callable

from snakeboot.transaction.transaction_definition import TransactionPhase

logger = logging.getLogger(__name__)

type Callback = Callable[[], None]


class TransactionSynchronizations:
    """The state of one physical transaction that a transaction manager keeps: rollback-only, and its callbacks.

    Like Spring's `TransactionSynchronizationManager` for one transaction. A savepoint opens a scope of its own: the
    callbacks registered inside a savepoint that rolls back are dropped, and so is the rollback-only mark set inside
    it, since its work is undone. A transaction manager calls `before_commit` while its transaction still runs, then
    `after_completion` once it ended.

    `before_commit` callbacks run inside the transaction: their failure rolls the transaction back. The callbacks after
    the end run robustly: the transaction already ended, so a failing callback is logged and the next one still runs;
    its error does not reach the caller of the transaction, whose committed work stays committed.
    """

    def __init__(self) -> None:
        self.rollback_only = False
        self._scopes: list[list[tuple[TransactionPhase, Callback]]] = [[]]
        self._rollback_only_before: list[bool] = []

    def register(self, phase: TransactionPhase, callback: Callback) -> None:
        """Runs `callback` in `phase` of this transaction, unless the savepoint that registered it rolls back."""
        self._scopes[-1].append((phase, callback))

    def begin_savepoint(self) -> None:
        """Opens the scope of a savepoint."""
        self._scopes.append([])
        self._rollback_only_before.append(self.rollback_only)

    def release_savepoint(self) -> None:
        """Hands the callbacks of the released savepoint to the scope around it."""
        released = self._scopes.pop()
        self._rollback_only_before.pop()
        self._scopes[-1].extend(released)

    def rollback_savepoint(self) -> None:
        """Drops the callbacks and the rollback-only mark of the savepoint that rolled back."""
        self._scopes.pop()
        self.rollback_only = self._rollback_only_before.pop()

    def before_commit(self) -> None:
        """Runs the `BEFORE_COMMIT` callbacks, those they register too; the first failure stops and propagates."""
        done = 0
        while done < len(waiting := self._of(TransactionPhase.BEFORE_COMMIT)):
            waiting[done]()
            done += 1

    def after_completion(self, *, committed: bool) -> None:
        """Runs, robustly, the `AFTER_COMMIT` or `AFTER_ROLLBACK` callbacks, then the `AFTER_COMPLETION` ones."""
        ending = TransactionPhase.AFTER_COMMIT if committed else TransactionPhase.AFTER_ROLLBACK
        for callback in [*self._of(ending), *self._of(TransactionPhase.AFTER_COMPLETION)]:
            run_robustly(callback)

    def _of(self, phase: TransactionPhase) -> list[Callback]:
        return [callback for scope in self._scopes for registered, callback in scope if registered is phase]


def run_robustly(callback: Callback) -> None:
    """Runs a callback after the end of a transaction: a failure is logged, and does not reach the caller.

    Unlike Spring's `TransactionSynchronization.afterCommit`, whose runtime exception reaches the caller of the
    commit: here the work committed, and the caller hears only of that. An effect that must happen belongs in an
    `@application_module_listener`, whose publication is kept until it succeeds.
    """
    try:
        callback()
    except Exception:
        logger.exception("A callback after the end of a transaction failed")
