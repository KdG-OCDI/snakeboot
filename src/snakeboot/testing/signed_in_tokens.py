import base64
import binascii
import json
from collections.abc import Iterable
from typing import Final

from snakeboot.security import Principal

TOKEN_PREFIX: Final = "snakeboot-test."
"""How a token of `signed_in_as` begins: only an application started for a test accepts it."""


def signed_in_as(name: str, *, roles: Iterable[str] = ()) -> dict[str, str]:
    """Returns the headers of a call by `name` with `roles`, like spring-security-test's `jwt()`, without Keycloak.

        client.post("/api/auctions", json=..., headers=signed_in_as("carol", roles={"auctioneer"}))

    An application started for a test (`TestApplication`, `@application_test`) accepts the token next to its own:
    the call is made by `Principal(name, roles)`, and the application's own `@roles_allowed` decide. Any other token
    still goes to the application's `BearerAuthentication`. A running application never accepts it.
    """
    return {"Authorization": f"Bearer {signed_in_token(Principal(name, frozenset(roles)))}"}


def signed_in_token(principal: Principal) -> str:
    """Returns the bearer token of `principal` that an application started for a test accepts."""
    claims = json.dumps({"name": principal.name, "roles": sorted(principal.roles)})
    return TOKEN_PREFIX + base64.urlsafe_b64encode(claims.encode()).decode()


def signed_in_principal(token: str) -> Principal | None:
    """Returns the principal of a token of `signed_in_as`, or None for any other token."""
    if not token.startswith(TOKEN_PREFIX):
        return None
    try:
        claims = json.loads(base64.urlsafe_b64decode(token.removeprefix(TOKEN_PREFIX)))
        return Principal(str(claims["name"]), frozenset(str(role) for role in claims["roles"]))
    except (binascii.Error, ValueError, KeyError, TypeError):
        return None
