"""`eventually` tries a check until it holds, like Awaitility: for what a thread of its own does."""

import itertools

import pytest

from snakeboot.testing import eventually


def test_a_predicate_is_tried_until_it_holds() -> None:
    calls = itertools.count(1)

    assert eventually(lambda: next(calls) >= 3, every=0) is True


def test_a_function_of_asserts_is_tried_until_it_passes_and_its_result_returned() -> None:
    calls = itertools.count(1)

    def the_third_call() -> int:
        call = next(calls)
        assert call == 3
        return call

    assert eventually(the_third_call, every=0) == 3


def test_a_check_that_never_holds_raises_its_last_failure() -> None:
    def never() -> None:
        raise AssertionError("still empty")

    with pytest.raises(AssertionError, match="still empty"):
        eventually(never, within=0.05, every=0.01)


def test_a_predicate_that_never_holds_says_so() -> None:
    with pytest.raises(AssertionError, match=r"did not hold within 0.05 seconds"):
        eventually(lambda: False, within=0.05, every=0.01)


def test_any_other_error_stops_at_once() -> None:
    calls = itertools.count(1)

    def broken() -> None:
        next(calls)
        raise KeyError("no such note")

    with pytest.raises(KeyError):
        eventually(broken)
    assert next(calls) == 2
