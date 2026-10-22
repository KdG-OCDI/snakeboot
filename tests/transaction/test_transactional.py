"""`@transactional` runs a use case inside the installed TransactionManager, or fails loudly."""

from collections.abc import Iterator

import pytest

from snakeboot.testing import RecordingTransactionManager
from snakeboot.transaction import (
    TransactionManagerNotInstalledError,
    TransactionManagerRegistry,
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
