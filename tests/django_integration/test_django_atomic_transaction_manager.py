"""`@transactional` on top of Django: a real commit, a real rollback, and after-commit side effects.

These tests use `transaction=True`: pytest-django then does not wrap each test in a
transaction of its own, so commits and on-commit callbacks happen as in production.
"""

from collections.abc import Iterator

import pytest

from snakeboot.django import DjangoAtomicTransactionManager
from snakeboot.transaction import TransactionManagerRegistry, after_commit, transactional
from tests.django_integration.notes.models import NoteRecord

pytestmark = pytest.mark.django_db(transaction=True)


class StoreNoteUseCase:
    """Stand-in for a use case: writes a row, defers a side effect, then may fail."""

    def __init__(self) -> None:
        self.side_effects: list[str] = []

    @transactional
    def execute(self, text: str, fail: bool) -> None:
        """Stores one row and plans a side effect after the commit."""
        NoteRecord.objects.create(text=text)
        after_commit(lambda: self.side_effects.append(text))
        if fail:
            raise RuntimeError("Failure after the write.")


@pytest.fixture(autouse=True)
def django_transactions() -> Iterator[None]:
    TransactionManagerRegistry.install(DjangoAtomicTransactionManager())
    yield
    TransactionManagerRegistry.uninstall()


def test_commits_the_write_and_then_runs_the_side_effect() -> None:
    use_case = StoreNoteUseCase()

    use_case.execute("committed", fail=False)

    assert NoteRecord.objects.filter(text="committed").exists()
    assert use_case.side_effects == ["committed"]


def test_rolls_back_the_write_and_drops_the_side_effect() -> None:
    use_case = StoreNoteUseCase()

    with pytest.raises(RuntimeError):
        use_case.execute("rolled back", fail=True)

    assert not NoteRecord.objects.filter(text="rolled back").exists()
    assert use_case.side_effects == []


def test_a_failing_side_effect_does_not_hide_the_committed_change() -> None:
    def failing_notification() -> None:
        raise ConnectionError("mail server down")

    @transactional
    def store_and_notify() -> str:
        NoteRecord.objects.create(text="kept")
        after_commit(failing_notification)
        return "done"

    assert store_and_notify() == "done"
    assert NoteRecord.objects.filter(text="kept").exists()
