from typing import override

from snakeboot.rest import BearerAuthentication
from snakeboot.security import Principal


class RoleTokens(BearerAuthentication):
    """Knows three tokens: an organizer's, a moderator's, and one of a caller without roles."""

    @override
    def authenticate(self, token: str) -> Principal | str | None:
        known: dict[str, Principal | str] = {
            "organizer-token": Principal("olivia", roles=frozenset({"organizer"})),
            "moderator-token": Principal("max", roles=frozenset({"moderator"})),
            "plain-token": "pat",
        }
        return known.get(token)
