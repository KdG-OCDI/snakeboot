import functools
import inspect
from collections.abc import Callable
from typing import Any

from django.http import HttpRequest, HttpResponse
from ninja import NinjaAPI
from wireup.integration.django import get_request_container

from snakeboot.rest.rest_controller_errors import InvalidRestControllerError

ControllerResolver = Callable[[type], object]
ErrorAnswer = Callable[[HttpRequest, Exception], HttpResponse]


def resolve_from_wireup_request_scope(controller_class: type) -> object:
    """Asks wireup for the controller during the current request; a singleton is the same object every time."""
    return get_request_container().get(controller_class)


class ControllerEndpointFactory:
    """Turns one controller or advice method into a function Django Ninja can call.

    Ninja inspects a view's signature to read path, query and body parameters. A method
    has `self` in front, which Ninja would take for a query parameter, so the endpoint
    shows Ninja the signature *without* `self`. When called, the endpoint asks the
    resolver for the controller instance and calls the method on it.

    Resolving per call (not once at start-up) keeps two things working: wireup's
    request scope under both WSGI and ASGI, and wireup overrides in tests.
    """

    def __init__(self, resolve_controller: ControllerResolver = resolve_from_wireup_request_scope) -> None:
        self._resolve_controller = resolve_controller

    def create(self, controller_class: type, method: Callable[..., Any]) -> Callable[..., Any]:
        """Returns the Ninja view for `method` of `controller_class`."""
        signature = inspect.signature(method)
        parameters_after_self = self._parameters_after_self(controller_class, method)
        resolve_controller = self._resolve_controller

        @functools.wraps(method)
        def endpoint(*args: Any, **kwargs: Any) -> Any:
            return method(resolve_controller(controller_class), *args, **kwargs)

        endpoint.__signature__ = signature.replace(parameters=parameters_after_self)  # type: ignore[attr-defined]
        return endpoint

    def create_error_answer(
        self, advice_class: type, method: Callable[..., Any], *, api: NinjaAPI, status: int
    ) -> ErrorAnswer:
        """Returns the Ninja exception handler that answers with `status` and the body `method` builds."""
        self._parameters_after_self(advice_class, method)
        resolve_advice = self._resolve_controller

        def answer(request: HttpRequest, error: Exception) -> HttpResponse:
            body = method(resolve_advice(advice_class), error)
            return api.create_response(request, body, status=status)

        return answer

    def _parameters_after_self(self, owner: type, method: Callable[..., Any]) -> list[inspect.Parameter]:
        if inspect.iscoroutinefunction(method):
            raise InvalidRestControllerError(
                f"{owner.__name__}.{method.__name__} is async; controller endpoints are synchronous."
            )
        parameters = list(inspect.signature(method).parameters.values())
        if not parameters or parameters[0].name != "self":
            raise InvalidRestControllerError(
                f"{owner.__name__}.{method.__name__} must be a regular method taking `self` first."
            )
        return parameters[1:]
