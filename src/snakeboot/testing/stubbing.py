from collections.abc import Callable
from unittest.mock import NonCallableMock


class Stubbing[**P, R]:
    """What `when(method)` returns: what a method of a mock or a spy answers from now on, in the types of its port."""

    def __init__(self, method: NonCallableMock) -> None:
        self._method = method

    def then_return(self, value: R) -> None:
        """The method returns `value`, of the type the port declares, like Mockito's `thenReturn`."""
        self._method.side_effect = None
        self._method.return_value = value

    def then_raise(self, error: BaseException) -> None:
        """The method raises `error`, like Mockito's `thenThrow`."""
        self._method.side_effect = error

    def then_answer(self, answer: Callable[P, R]) -> None:
        """The method answers what `answer` returns for the same arguments, like Mockito's `thenAnswer`."""
        self._method.side_effect = answer


class Verification[**P, R]:
    """What `verify(method)` returns: how a method of a mock or a spy was called, in the types of its port."""

    def __init__(self, method: NonCallableMock) -> None:
        self._method = method

    def called_once_with(self, *args: P.args, **kwargs: P.kwargs) -> None:
        """The method was called once, with these arguments, like Mockito's `verify(mock).method(...)`."""
        self._method.assert_called_once_with(*args, **kwargs)

    def called_with(self, *args: P.args, **kwargs: P.kwargs) -> None:
        """One of the calls of the method had these arguments."""
        self._method.assert_any_call(*args, **kwargs)

    def called_times(self, count: int) -> None:
        """The method was called `count` times, like Mockito's `times(count)`."""
        if self._method.call_count != count:
            raise AssertionError(f"{self._method} was called {self._method.call_count} times, not {count}.")

    def never_called(self) -> None:
        """The method was not called, like Mockito's `never()`."""
        self._method.assert_not_called()


def when[**P, R](method: Callable[P, R]) -> Stubbing[P, R]:
    """Says what a method of a `MockComponent` or a `SpyComponent` answers, like Mockito's `when(...)`.

        when(self.invoices.exists_for_auction).then_return(False)
        when(self.invoices.save).then_raise(ConnectionError("down"))

    A type checker holds the answer to the port's own return type: `then_return("no")` for a `bool` is refused.
    """
    return Stubbing[P, R](_mock_of(method))


def verify[**P, R](method: Callable[P, R]) -> Verification[P, R]:
    """Checks how a method of a `MockComponent` or a `SpyComponent` was called, like Mockito's `verify(...)`.

        verify(self.invoices.save).called_once_with(invoice)
        verify(self.shipments.request).never_called()

    A type checker holds the arguments to the port's own parameters, where Mockito's `any()` checks nothing.
    """
    return Verification[P, R](_mock_of(method))


def _mock_of(method: object) -> NonCallableMock:
    if not isinstance(method, NonCallableMock):
        raise TypeError(f"{method!r} is no method of a MockComponent or a SpyComponent: only a mock is stubbed.")
    return method
