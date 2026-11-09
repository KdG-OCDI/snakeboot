from abc import ABC, abstractmethod
from typing import Any, Final, override

from wireup import injectable

from snakeboot.security import Principal

AUTHENTICATION_MARKER_ATTRIBUTE: Final = "__rest_bearer_authentication__"
"""Set on every subclass that became a component, so the controller scan finds the API's authentication."""


class BearerAuthentication(ABC):
    """Checks the bearer token of every call to the API, like a `SecurityFilterChain` bean in Spring Boot.

    Extend it in an adapter of the component scan. The subclass is a component of the container, registered as
    `BearerAuthentication`, so its constructor receives sections and ports by type like any adapter. Every endpoint
    then needs `Authorization: Bearer <token>`; `/health` stays open, and an endpoint opts out with
    `@route.get(..., public=True)`. An endpoint learns who called with a parameter of type `Principal`, and
    `@roles_allowed` lets only callers with one of its roles in.

        class KeycloakTokens(BearerAuthentication):
            def __init__(self, properties: SecurityProperties) -> None: ...

            @override
            def authenticate(self, token: str) -> Principal | None:
                ...  # Principal(subject, roles=...) for a valid token, or None
    """

    @override
    def __init_subclass__(cls, *, component: bool = True, **kwargs: Any) -> None:
        """Registers a concrete subclass; `component=False` marks a base meant to be extended, such as
        JwtBearerAuthentication, so a module that imports it to extend it does not hold two components."""
        super().__init_subclass__(**kwargs)
        if component and not getattr(cls.authenticate, "__isabstractmethod__", False):
            setattr(cls, AUTHENTICATION_MARKER_ATTRIBUTE, True)
            injectable(cls, as_type=BearerAuthentication)

    @abstractmethod
    def authenticate(self, token: str) -> Principal | str | None:
        """Returns whoever presents `token`, or None to answer 401.

        A `Principal` carries the caller's id and roles; a plain id is a principal without roles. An endpoint receives
        it as its `Principal` parameter.
        """
