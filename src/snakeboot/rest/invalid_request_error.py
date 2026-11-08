from collections.abc import Sequence
from dataclasses import dataclass
from typing import override


@dataclass(frozen=True, slots=True)
class RequestProblem:
    """One thing wrong with a call: where it is (`("body", "move", "played_at")`) and what is wrong with it."""

    location: tuple[str, ...]
    message: str

    @override
    def __str__(self) -> str:
        """`body.move.played_at: Input should be a valid datetime`."""
        return f"{'.'.join(self.location)}: {self.message}"


class InvalidRequestError(ValueError):
    """Raised when a call does not fit its endpoint, like Spring's `MethodArgumentNotValidException`.

    A missing field, a wrong type, a value the body or query parameters cannot hold: the web framework finds it
    before the endpoint runs, and raises this in no framework's terms. An advice answers it like any error, and
    `error_answer(error)` makes it `{"code": "invalid_request", "detail": ...}`:

        @exception_handler(InvalidRequestError, status=422)
        def answer_invalid_request(self, error: Exception) -> dict[str, str]:
            return error_answer(error)

    Without such an advice the framework answers with 422 in its own words.
    """

    def __init__(self, problems: Sequence[RequestProblem]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(str(problem) for problem in self.problems) or "The call does not fit the endpoint.")
