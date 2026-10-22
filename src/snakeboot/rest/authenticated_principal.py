from django.http import HttpRequest

from snakeboot.rest.rest_controller_errors import NoAuthenticatedPrincipalError


def authenticated_principal(request: HttpRequest) -> str:
    """Returns the id that the API's authentication stored on `request.auth` (Spring: `@AuthenticationPrincipal`).

    Ninja adds `auth` to the request at run time, so a type checker cannot see it. This is
    the one place that reads it, so controllers stay fully typed.
    """
    principal = request.auth  # type: ignore[attr-defined]
    if not isinstance(principal, str):
        raise NoAuthenticatedPrincipalError(f"Expected the id of a signed-in principal, got {principal!r}.")
    return principal
