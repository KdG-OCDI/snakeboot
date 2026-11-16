"""`@transactional` runs a use case inside the installed TransactionManager, or fails loudly."""

import contextlib
from collections.abc import Callable, Iterator

import pytest

from snakeboot.testing import RecordingTransactionManager
from snakeboot.transaction import (
    Isolation,
    Propagation,
    TransactionManagerNotInstalledError,
    TransactionManagerRegistry,
    UnexpectedRollbackError,
    after_commit,
    transactional,
)


class RenameUseCase:
    """Minimal stand-in for a state-changing use case."""

    def __init__(self) -> None:
        self.name = "old"

    @transactional
    def execute(self, new_name: str) -> str:
        """Renames, or fails for an empty name, to exercise commit and rollback."""
        if not new_name:
            raise ValueError("A name cannot be empty.")
        self.name = new_name
        return self.name


@pytest.fixture
def transaction_manager() -> Iterator[RecordingTransactionManager]:
    manager = RecordingTransactionManager()
    TransactionManagerRegistry.install(manager)
    yield manager
    TransactionManagerRegistry.uninstall()


def test_commits_when_the_operation_returns(transaction_manager: RecordingTransactionManager) -> None:
    assert RenameUseCase().execute("new") == "new"

    assert (transaction_manager.opened, transaction_manager.committed, transaction_manager.rolled_back) == (1, 1, 0)


def test_rolls_back_and_reraises_when_the_operation_fails(
    transaction_manager: RecordingTransactionManager,
) -> None:
    with pytest.raises(ValueError, match="empty"):
        RenameUseCase().execute("")

    assert (transaction_manager.opened, transaction_manager.committed, transaction_manager.rolled_back) == (1, 0, 1)


def test_keeps_the_name_and_docstring_of_the_method() -> None:
    assert RenameUseCase.execute.__name__ == "execute"
    assert "commit and rollback" in (RenameUseCase.execute.__doc__ or "")


class NotifyingUseCase:
    """Stand-in for a use case with a side effect outside the database."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    @transactional
    def execute(self, message: str, fail: bool) -> None:
        """Defers sending `message` until commit, then fails on request."""
        after_commit(lambda: self.sent.append(message))
        if fail:
            raise ValueError("Something went wrong after the side effect was planned.")


def test_after_commit_runs_the_side_effect_once_committed(
    transaction_manager: RecordingTransactionManager,
) -> None:
    use_case = NotifyingUseCase()

    use_case.execute("promoted", fail=False)

    assert use_case.sent == ["promoted"]


def test_after_commit_drops_the_side_effect_on_rollback(
    transaction_manager: RecordingTransactionManager,
) -> None:
    use_case = NotifyingUseCase()

    with pytest.raises(ValueError, match="went wrong"):
        use_case.execute("promoted", fail=True)

    assert use_case.sent == []


def test_fails_when_composition_installed_no_manager() -> None:
    TransactionManagerRegistry.uninstall()

    with pytest.raises(TransactionManagerNotInstalledError):
        RenameUseCase().execute("new")


def test_refuses_async_operation_at_decoration_time() -> None:
    async def async_use_case() -> None:
        pass

    with pytest.raises(TypeError, match="async function"):
        transactional(async_use_case)


def test_refuses_operation_returning_coroutine(transaction_manager: RecordingTransactionManager) -> None:
    def returns_coroutine() -> object:
        async def inner() -> None:
            pass

        return inner()

    wrapped = transactional(returns_coroutine)
    with pytest.raises(TypeError, match="returned a coroutine"):
        wrapped()


def test_failing_after_commit_callback_does_not_prevent_other_callbacks_or_mask_commit(
    transaction_manager: RecordingTransactionManager,
) -> None:
    executed: list[str] = []

    def failing_callback() -> None:
        executed.append("first")
        raise RuntimeError("Email service crashed")

    def second_callback() -> None:
        executed.append("second")

    class MultiCallbackUseCase:
        @transactional
        def execute(self) -> str:
            after_commit(failing_callback)
            after_commit(second_callback)
            return "success"

    result = MultiCallbackUseCase().execute()

    assert result == "success"
    assert executed == ["first", "second"]
    assert transaction_manager.committed == 1
    assert len(transaction_manager.callback_errors) == 1
    assert str(transaction_manager.callback_errors[0]) == "Email service crashed"


class Ledger:
    """Composes transactional calls the way services do: an outer one that calls inner ones and may catch."""

    def __init__(self) -> None:
        self.inner_ran_in_transaction: list[bool] = []

    @transactional
    def outer(self, inner: Callable[[], None]) -> None:
        with contextlib.suppress(ValueError):
            inner()

    @transactional
    def joined_failure(self) -> None:
        raise ValueError("inner failed")

    @transactional(propagation=Propagation.NESTED)
    def nested_failure(self) -> None:
        raise ValueError("inner failed")

    @transactional(propagation=Propagation.REQUIRES_NEW)
    def independent_failure(self) -> None:
        raise ValueError("inner failed")

    @transactional(no_rollback_for=(ValueError,))
    def tolerated_failure(self) -> None:
        raise ValueError("tolerated")

    def calls_through_self(self) -> None:
        self.inner()

    @transactional
    def inner(self) -> None:
        self.inner_ran_in_transaction.append(TransactionManagerRegistry.current().in_transaction)


def test_a_caught_failure_of_a_joined_call_rolls_the_whole_transaction_back(
    transaction_manager: RecordingTransactionManager,
) -> None:
    ledger = Ledger()

    with pytest.raises(UnexpectedRollbackError):
        ledger.outer(ledger.joined_failure)

    assert (transaction_manager.opened, transaction_manager.committed, transaction_manager.rolled_back) == (1, 0, 1)


def test_a_caught_failure_of_a_nested_call_lets_the_outer_transaction_commit(
    transaction_manager: RecordingTransactionManager,
) -> None:
    ledger = Ledger()

    ledger.outer(ledger.nested_failure)

    assert (transaction_manager.opened, transaction_manager.committed, transaction_manager.rolled_back) == (1, 1, 0)


def test_a_failing_independent_call_rolls_back_alone(transaction_manager: RecordingTransactionManager) -> None:
    ledger = Ledger()

    ledger.outer(ledger.independent_failure)

    assert (transaction_manager.opened, transaction_manager.committed, transaction_manager.rolled_back) == (2, 1, 1)


def test_an_exception_named_in_no_rollback_for_does_not_mark_the_transaction(
    transaction_manager: RecordingTransactionManager,
) -> None:
    ledger = Ledger()

    ledger.outer(ledger.tolerated_failure)
    with pytest.raises(ValueError, match="tolerated"):
        ledger.tolerated_failure()

    assert (transaction_manager.opened, transaction_manager.committed, transaction_manager.rolled_back) == (2, 2, 0)


def test_a_transactional_method_called_through_self_runs_in_a_transaction(
    transaction_manager: RecordingTransactionManager,
) -> None:
    ledger = Ledger()

    ledger.calls_through_self()

    assert ledger.inner_ran_in_transaction == [True]
    assert transaction_manager.committed == 1


def test_after_commit_inside_a_joined_call_waits_for_the_outermost_commit(
    transaction_manager: RecordingTransactionManager,
) -> None:
    heard: list[str] = []

    @transactional
    def inner() -> None:
        after_commit(lambda: heard.append("committed"))

    @transactional
    def outer() -> None:
        inner()
        heard.append("inner returned")

    outer()

    assert heard == ["inner returned", "committed"]


def test_the_decorator_keeps_its_attributes_apart_per_method() -> None:
    @transactional(read_only=True, isolation=Isolation.SERIALIZABLE)
    def report() -> str:
        """Reads only."""
        return "report"

    assert report.__name__ == "report"
    assert report.__doc__ == "Reads only."
