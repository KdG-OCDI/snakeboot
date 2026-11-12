from pydantic import BaseModel

from snakeboot.rest import rest_controller, roles_allowed, route
from snakeboot.security import Principal
from tests.pytest_testing.library.loans.lend_book import LendBook, LoanDTO


class NewLoanDTO(BaseModel):
    isbn: str


@rest_controller("/loans")
class LoanRestController:
    def __init__(self, lend_book: LendBook) -> None:
        self._lend_book = lend_book

    @route.post("", status=201)
    @roles_allowed("member")
    def lend(self, body: NewLoanDTO, member: Principal) -> LoanDTO:
        return self._lend_book.execute(body.isbn, member.name)
