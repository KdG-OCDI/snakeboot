"""`when` and `verify` stub and check a mock in the types of its port, like Mockito's `when` and `verify`."""

from abc import ABC, abstractmethod
from typing import override
from unittest.mock import create_autospec

import pytest

from snakeboot.testing import verify, when


class Ledger(ABC):
    @abstractmethod
    def balance_of(self, account: str) -> int: ...

    @abstractmethod
    def book(self, account: str, amount: int) -> None: ...


def a_mock() -> Ledger:
    ledger: Ledger = create_autospec(Ledger, instance=True)
    return ledger


def test_then_return_says_what_the_method_answers() -> None:
    ledger = a_mock()

    when(ledger.balance_of).then_return(120)

    assert ledger.balance_of("ann") == 120


def test_then_raise_makes_the_method_raise_and_then_return_undoes_it() -> None:
    ledger = a_mock()
    when(ledger.book).then_raise(ConnectionError("The ledger is down."))

    with pytest.raises(ConnectionError):
        ledger.book("ann", 10)

    when(ledger.book).then_return(None)
    ledger.book("ann", 10)


def test_then_answer_answers_with_the_arguments() -> None:
    ledger = a_mock()

    def letters_in(account: str) -> int:
        return len(account)

    when(ledger.balance_of).then_answer(letters_in)

    assert ledger.balance_of("bob") == 3


def test_verify_checks_the_calls() -> None:
    ledger = a_mock()
    ledger.book("ann", 10)
    ledger.book("bob", 20)

    verify(ledger.book).called_with("ann", 10)
    verify(ledger.book).called_times(2)
    verify(ledger.balance_of).never_called()
    with pytest.raises(AssertionError):
        verify(ledger.book).called_once_with("ann", 10)
    with pytest.raises(AssertionError, match="called 2 times, not 3"):
        verify(ledger.book).called_times(3)


def test_a_type_checker_holds_the_answers_and_the_arguments_to_the_port() -> None:
    ledger = a_mock()

    # mypy refuses both lines; an unneeded ignore would fail mypy (warn_unused_ignores), so they check the types.
    when(ledger.balance_of).then_return("a lot")  # type: ignore[arg-type]
    ledger.book("ann", 10)
    with pytest.raises(AssertionError):
        verify(ledger.book).called_once_with("ann", "ten")  # type: ignore[arg-type]


def test_only_a_mock_is_stubbed() -> None:
    class RealLedger(Ledger):
        @override
        def balance_of(self, account: str) -> int:
            return 0

        @override
        def book(self, account: str, amount: int) -> None:
            pass

    with pytest.raises(TypeError, match="no method of a MockComponent"):
        when(RealLedger().balance_of)
