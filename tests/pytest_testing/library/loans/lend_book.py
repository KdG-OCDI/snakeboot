from collections import Counter

from pydantic import BaseModel

from snakeboot.stereotype import component
from tests.pytest_testing.library.catalogue.catalogue import Catalogue
from tests.pytest_testing.library.loans.loan_properties import LoanProperties


class LoanDTO(BaseModel):
    isbn: str
    member: str


class BookNotOnTheShelfError(LookupError):
    """The book is not on the shelf."""


class TooManyLoansError(ValueError):
    """The member has as many books as `[loans] max_loans` allows."""


@component
class LendBook:
    """The use case: a member borrows a book that is on the shelf, up to `[loans] max_loans` at once."""

    def __init__(self, catalogue: Catalogue, properties: LoanProperties) -> None:
        self._catalogue = catalogue
        self._max_loans = properties.max_loans
        self._loans: Counter[str] = Counter()

    def execute(self, isbn: str, member: str) -> LoanDTO:
        """Lends the book `isbn` to `member`."""
        if not self._catalogue.is_on_the_shelf(isbn):
            raise BookNotOnTheShelfError(f"{isbn} is not on the shelf.")
        if self._loans[member] >= self._max_loans:
            raise TooManyLoansError(f"{member} has {self._max_loans} books already.")
        self._loans[member] += 1
        return LoanDTO(isbn=isbn, member=member)
