from collections.abc import Callable
from typing import Annotated, Final

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from snakeboot.rest import BearerAuthentication

type ComponentResolver = Callable[[type], object]
"""Finds the component of a type for a call: the container's `get`, or a test's stand-in."""

BEARER_SCHEME: Final = HTTPBearer(scheme_name="BearerToken", auto_error=False)
"""Reads `Authorization: Bearer <token>`; a call without it reaches `BearerToken`, which answers 401 itself.

The OpenAPI document names the scheme `BearerToken`, as it did on Django Ninja.
"""


class BearerToken:
    """FastAPI's security dependency of the API: it asks the container's `BearerAuthentication`, once per call.

    It returns the id of whoever presents the token; a call without a token, or with one the authentication refuses,
    is answered with 401 and `WWW-Authenticate: Bearer`.
    """

    def __init__(self, resolve: ComponentResolver) -> None:
        self._resolve = resolve

    def __call__(self, credentials: Annotated[HTTPAuthorizationCredentials | None, Security(BEARER_SCHEME)]) -> str:
        """Returns the id of the caller, or raises the 401 answer."""
        name = self._authentication().authenticate(credentials.credentials) if credentials is not None else None
        if name is None:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, detail="Unauthorized", headers={"WWW-Authenticate": "Bearer"}
            )
        return name

    def _authentication(self) -> BearerAuthentication:
        authentication = self._resolve(BearerAuthentication)
        if not isinstance(authentication, BearerAuthentication):
            raise TypeError(f"The container gave {authentication!r} as the BearerAuthentication.")
        return authentication
