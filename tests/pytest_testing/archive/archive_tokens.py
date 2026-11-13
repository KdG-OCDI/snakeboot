from typing import override

from snakeboot.rest import BearerAuthentication
from snakeboot.security import Principal
from tests.pytest_testing.archive.clerks import ClerkRecords


class ArchiveTokens(BearerAuthentication):
    """The keys of the clerks, as the database keeps them: an authentication that asks a repository."""

    def __init__(self, clerks: ClerkRecords) -> None:
        self._clerks = clerks

    @override
    def authenticate(self, token: str) -> Principal | None:
        clerk = self._clerks.find_by_id(token)
        return None if clerk is None else Principal(clerk.name, frozenset({"clerk"}))
