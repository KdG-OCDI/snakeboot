import functools
import inspect
from collections.abc import Callable
from typing import Any, Final

from django.http import HttpRequest, HttpResponse
from ninja import NinjaAPI
from wireup import ScopedSyncContainer
from wireup.integration.django import get_request_container

from snakeboot.rest import DeclaredEndpoint, DeclaredErrorHandler, NoAuthenticatedPrincipalError, Principal

ComponentResolver = Callable[[type], object]
ErrorAnswer = Callable[[HttpRequest, Exception], HttpResponse]

_REQUEST: Final = inspect.Parameter("request", inspect.Parameter.POSITIONAL_OR_KEYWORD)
"""The first parameter of every Ninja view; Ninja recognises it by name and fills it with the request."""


def resolve_from_wireup_request_scope(component_type: type) -> object:
    """Asks wireup for a component during the current request; a singleton is the same object every time.

    Under WSGI the request scope is synchronous. Under ASGI it is asynchronous, and its `get` returns a coroutine; a
    controller endpoint is synchronous, so it resolves synchronously, as wireup's own class-based views do.
    """
    scope = get_request_container()
    if isinstance(scope, ScopedSyncContainer):
        return scope.get(component_type)
    return scope._synchronous_get(component_type)  # reason: wireup resolves its sync views so under ASGI


def principal_of(request: HttpRequest) -> Principal:
    """Returns whoever the API's authentication found for this call: Ninja stores the id on `request.auth`."""
    name = getattr(request, "auth", None)
    if not isinstance(name, str):
        raise NoAuthenticatedPrincipalError(f"Expected the id of a signed-in principal, got {name!r}.")
    return Principal(name)


class NinjaEndpointFactory:
    """Turns the endpoints and error answers of the controller scan into the functions Django Ninja calls.

    Ninja reads a view's signature to find path, query and body parameters, and passes the request first. A view
    built here shows Ninja `request` followed by the parameters the call carries, and hides `self` and every
    `Principal` parameter. When called, it asks the resolver for the controller, fills the principals from the
    request, and calls the method; the request itself never reaches the controller.

    Resolving per call (not once at start-up) keeps two things working: wireup's request scope under both WSGI and
    ASGI, and wireup overrides in tests.
    """

    def __init__(self, resolve: ComponentResolver = resolve_from_wireup_request_scope) -> None:
        self._resolve = resolve

    def create(self, endpoint: DeclaredEndpoint) -> Callable[..., Any]:
        """Returns the Ninja view of `endpoint`."""
        method, owner = endpoint.method, endpoint.controller_class
        principal_parameters = endpoint.signature.principal_parameters
        resolve = self._resolve

        @functools.wraps(method)
        def view(request: HttpRequest, **values: Any) -> Any:
            principals = {name: principal_of(request) for name in principal_parameters}
            return method(resolve(owner), **values, **principals)

        view.__signature__ = inspect.Signature([_REQUEST, *endpoint.signature.parameters])  # type: ignore[attr-defined]
        return view

    def create_error_answer(self, handler: DeclaredErrorHandler, api: NinjaAPI) -> ErrorAnswer:
        """Returns the Ninja exception handler that answers with the status and the body of `handler`."""
        method, owner, status = handler.method, handler.advice_class, handler.mapping.status
        resolve = self._resolve

        def answer(request: HttpRequest, error: Exception) -> HttpResponse:
            body = method(resolve(owner), error)
            return api.create_response(request, body, status=status)

        return answer
