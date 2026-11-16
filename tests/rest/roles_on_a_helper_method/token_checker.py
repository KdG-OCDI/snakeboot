from typing import override

from snakeboot.rest import BearerAuthentication


class TokenChecker(BearerAuthentication):
    """Accepts one token, as a test double of a real token check."""

    @override
    def authenticate(self, token: str) -> str | None:
        return "alice" if token == "good-token" else None
