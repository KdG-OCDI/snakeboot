from collections.abc import Callable
from typing import Annotated, Final

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from snakeboot.rest import BearerAuthentication, NoAuthenticatedPrincipalError
from snakeboot.security import Principal

type ComponentResolver = Callable[[type], object]
"""Finds the component of a type for a call: the container's `get`, or a test's stand-in."""

BEARER_SCHEME: Final = HTTPBearer(scheme_name="BearerToken", auto_error=False)
"""Reads `Authorization: Bearer <token>`; a call without it reaches `BearerToken`, which answers 401 itself.

The OpenAPI document names the scheme `BearerToken`, as it did on Django Ninja.
"""


class BearerToken:
    """FastAPI's security dependency of the API: it asks the container's `BearerAuthentication`, once per call.

    It returns the `Principal` of whoever presents the token; a call without a token, or with one the authentication
    refuses, is answered with 401 and `WWW-Authenticate: Bearer`. With `roles`, a caller with none of them is answered
    with 403, like Spring Security's `AccessDeniedException`.
    """

    def __init__(self, resolve: ComponentResolver, roles: frozenset[str] = frozenset()) -> None:
        self._resolve = resolve
        self._roles = roles

    def requiring(self, roles: frozenset[str]) -> "BearerToken":
        """Returns the dependency of an endpoint that lets in only callers with one of `roles`, or any when empty."""
        return self if roles == self._roles else BearerToken(self._resolve, roles)

    def __call__(
        self, credentials: Annotated[HTTPAuthorizationCredentials | None, Security(BEARER_SCHEME)]
    ) -> Principal:
        """Returns the principal of the caller, or raises the 401 or the 403 answer."""
        found = self._authentication().authenticate(credentials.credentials) if credentials is not None else None
        if found is None:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, detail="Unauthorized", headers={"WWW-Authenticate": "Bearer"}
            )
        principal = principal_of(found)
        if self._roles and not principal.has_any_role(self._roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return principal

    def _authentication(self) -> BearerAuthentication:
        authentication = self._resolve(BearerAuthentication)
        if not isinstance(authentication, BearerAuthentication):
            raise TypeError(f"The container gave {authentication!r} as the BearerAuthentication.")
        return authentication


def principal_of(found: object) -> Principal:
    """Returns what a `BearerAuthentication` found as a `Principal`: a plain id is a principal without roles."""
    if isinstance(found, Principal):
        return found
    if isinstance(found, str):
        return Principal(found)
    raise NoAuthenticatedPrincipalError(f"Expected a Principal or the id of a signed-in principal, got {found!r}.")
