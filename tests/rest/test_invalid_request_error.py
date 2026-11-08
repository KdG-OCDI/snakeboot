"""An invalid request is an error in snakeboot's terms, which an advice answers like any other."""

from snakeboot.rest import InvalidRequestError, RequestProblem, error_answer


def test_its_message_names_every_problem_where_it_is() -> None:
    error = InvalidRequestError(
        [RequestProblem(("body", "played_at"), "not a datetime"), RequestProblem(("query", "limit"), "too big")]
    )

    assert str(error) == "body.played_at: not a datetime; query.limit: too big"


def test_error_answer_gives_it_the_code_invalid_request() -> None:
    error = InvalidRequestError([RequestProblem(("body", "state"), "Field required")])

    assert error_answer(error) == {"code": "invalid_request", "detail": "body.state: Field required"}


def test_without_problems_it_still_says_what_is_wrong() -> None:
    assert str(InvalidRequestError([])) == "The call does not fit the endpoint."
