from snakeboot.rest import error_answer, exception_handler, rest_controller_advice
from tests.pytest_testing.library.loans.lend_book import BookNotOnTheShelfError, TooManyLoansError


@rest_controller_advice
class LoanErrorAdvice:
    @exception_handler(BookNotOnTheShelfError, TooManyLoansError, status=409)
    def answer_conflict(self, error: Exception) -> dict[str, str]:
        return error_answer(error)
