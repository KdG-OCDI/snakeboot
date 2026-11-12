from typing import override

from snakeboot.rest import BearerAuthentication
from snakeboot.security import Principal


class LibraryTokens(BearerAuthentication):
    """The library's own tokens, as its authorization server would give them: here, mia's, a member."""

    @override
    def authenticate(self, token: str) -> Principal | None:
        return Principal("mia", frozenset({"member"})) if token == "mia-token" else None
