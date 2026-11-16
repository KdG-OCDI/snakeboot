from collections.abc import Callable
from typing import Final

from snakeboot.rest.rest_controller_errors import InvalidRestControllerError

ROLES_ATTRIBUTE: Final = "__rest_roles_allowed__"
"""Set on a controller class or an endpoint method by `@roles_allowed`: the roles of which a caller needs one."""


def roles_allowed[T](*roles: str) -> Callable[[T], T]:
    """Lets only a caller with one of `roles` call an endpoint, like Jakarta's `@RolesAllowed` in Spring Security.

        @rest_controller("/admin")
        @roles_allowed("admin")                       # every endpoint of the controller
        class AdminRestController:
            @route.get("/games")
            def games(self) -> list[GameDTO]: ...

            @route.delete("/games/{game_id}")
            @roles_allowed("admin", "moderator")      # an endpoint's own roles replace the controller's
            def delete_game(self, game_id: str) -> None: ...

    A caller with a valid token but none of the roles is answered with 403; `Principal.roles` holds the roles the
    `BearerAuthentication` found in the token. A public endpoint, or roles without a `BearerAuthentication` in the
    component scan, stop the start.

    It protects HTTP endpoints only: the decorator marks, and the binding checks the roles when it dispatches a
    request. Unlike Spring's method security (`@EnableMethodSecurity(jsr250Enabled = true)`), nothing checks a direct
    call of a service, a command or a listener; so `@roles_allowed` on a class that is no `@rest_controller`, or on a
    method that is no `@route`, stops the start instead of looking like protection.
    """
    if not roles or not all(roles):
        raise InvalidRestControllerError(f"@roles_allowed names one role or more, got {roles!r}.")

    def mark(target: T) -> T:
        setattr(target, ROLES_ATTRIBUTE, frozenset(roles))
        return target

    return mark


def roles_of(controller_class: type, method: Callable[..., object]) -> frozenset[str]:
    """Returns the roles of which a caller of `method` needs one: its own, else its controller's, else none."""
    own: frozenset[str] | None = getattr(method, ROLES_ATTRIBUTE, None)
    if own is not None:
        return own
    inherited: frozenset[str] = getattr(controller_class, ROLES_ATTRIBUTE, frozenset())
    return inherited
