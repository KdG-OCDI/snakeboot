import functools
import inspect
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from typing import Any, Final

from fastapi import Request, Security
from fastapi.encoders import jsonable_encoder
from starlette.responses import JSONResponse, Response

from snakeboot.fastapi_web.bearer_token import BearerToken, ComponentResolver, principal_of
from snakeboot.fastapi_web.event_stream import event_stream_response
from snakeboot.rest import DeclaredEndpoint, DeclaredErrorHandler, ServerSentEvents
from snakeboot.security import Principal, SecurityContext

type ErrorAnswer = Callable[[Request, Exception], Response]

PRINCIPAL_PARAMETER: Final = "snakeboot_principal"
"""The hidden parameter through which FastAPI hands a view the `Principal` that the `BearerToken` found."""


class FastApiEndpointFactory:
    """Turns the endpoints and error answers of the controller scan into the functions FastAPI calls.

    FastAPI reads a view's signature to find path, query and body parameters. A view built here shows FastAPI the
    parameters the call carries, and hides `self` and every `Principal` parameter; an endpoint that needs a signed-in
    caller gets the `BearerToken` of its roles as a security dependency instead. When called, the view asks the
    resolver for the controller, fills the principals and calls the method with the caller signed in to the
    `SecurityContext`. `ServerSentEvents` become a streamed response, `None` (`-> None`) an empty one; FastAPI renders
    any other answer with the endpoint's response model.

    Resolving per call (not once at start-up) keeps a test's overrides working.
    """

    def __init__(self, resolve: ComponentResolver, bearer_token: BearerToken | None) -> None:
        self._resolve = resolve
        self._bearer_token = bearer_token

    def create(self, endpoint: DeclaredEndpoint) -> Callable[..., Any]:
        """Returns the FastAPI view of `endpoint`."""
        method, owner, signature = endpoint.method, endpoint.controller_class, endpoint.signature
        status, resolve = endpoint.route_mapping.status, self._resolve

        @functools.wraps(method)
        def view(**values: Any) -> Any:
            caller = values.pop(PRINCIPAL_PARAMETER, None)
            principals = {parameter: principal_of(caller) for parameter in signature.principal_parameters}
            with _signed_in(caller):
                answer = method(resolve(owner), **values, **principals)
            if isinstance(answer, ServerSentEvents):
                return event_stream_response(answer, status)
            return Response(status_code=status) if signature.response is None else answer

        view.__signature__ = inspect.Signature(self._parameters_of(endpoint))  # type: ignore[attr-defined]
        return view

    def create_error_answer(self, handler: DeclaredErrorHandler) -> ErrorAnswer:
        """Returns the exception handler that answers with the status and the body of `handler`."""
        method, owner, status, resolve = handler.method, handler.advice_class, handler.mapping.status, self._resolve

        def answer(_request: Request, error: Exception) -> Response:
            return JSONResponse(jsonable_encoder(method(resolve(owner), error)), status_code=status)

        return answer

    def _parameters_of(self, endpoint: DeclaredEndpoint) -> list[inspect.Parameter]:
        # Keyword-only, so a parameter with a default may come before one without, as in the method.
        parameters = [
            parameter.replace(kind=inspect.Parameter.KEYWORD_ONLY) for parameter in endpoint.signature.parameters
        ]
        if self._bearer_token is not None and not endpoint.route_mapping.public:
            parameters.append(
                inspect.Parameter(
                    PRINCIPAL_PARAMETER,
                    inspect.Parameter.KEYWORD_ONLY,
                    default=Security(self._bearer_token.requiring(endpoint.roles)),
                    annotation=Principal,
                )
            )
        return parameters


def _signed_in(caller: object) -> AbstractContextManager[object]:
    return SecurityContext.signed_in(caller) if isinstance(caller, Principal) else nullcontext()
