from collections.abc import Callable, Mapping
from typing import Any, Final

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response

from snakeboot.component_scan import ComponentScan, application_package
from snakeboot.configuration import ServerProperties
from snakeboot.fastapi_web.bearer_token import BearerToken, ComponentResolver
from snakeboot.fastapi_web.event_stream import EventStreamResponse
from snakeboot.fastapi_web.fastapi_endpoint_factory import ErrorAnswer, FastApiEndpointFactory
from snakeboot.openapi import openapi_definition_of
from snakeboot.rest import (
    UNDECLARED,
    ControllerScan,
    DeclaredEndpoint,
    InvalidRequestError,
    RequestProblem,
    ScannedControllers,
    ServerSentEvents,
)

API_PREFIX: Final = "/api"
"""Where the REST API lives; its OpenAPI document is /api/openapi.json and Swagger UI /api/docs."""

HEALTH_PATH: Final = "/health"
"""The liveness probe, outside the API: it answers without authentication."""


def rest_api(application: type, resolve: ComponentResolver, *, server: ServerProperties | None = None) -> FastAPI:
    """Returns the REST API of `application` on FastAPI: every controller and advice of its component scan.

    The title, version and description come from `@openapi_definition` on the application class. When the component
    scan holds a `BearerAuthentication`, every endpoint that is not public asks it for the bearer token. `server`
    turns on FastAPI's debug answers and accepts only its `allowed_hosts`; without it, as in a test, every host is
    accepted. `resolve` finds a component for a call: the container's `get`, or a test's.
    """
    scanned = ControllerScan(ComponentScan.of(application)).find()
    api = FastAPI(
        **_description_of(application),
        debug=server.debug if server is not None else False,
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
        redoc_url=None,
    )
    bearer_token = BearerToken(resolve) if scanned.authentication is not None else None
    add_routes(api, scanned, FastApiEndpointFactory(resolve, bearer_token))
    api.add_api_route(HEALTH_PATH, _health_of(application), methods=["GET"], include_in_schema=False)
    if server is not None:
        api.add_middleware(TrustedHostMiddleware, allowed_hosts=list(server.allowed_hosts))
    return api


def add_routes(api: FastAPI, scanned: ScannedControllers, endpoint_factory: FastApiEndpointFactory) -> None:
    """Adds one router per controller under /api, and the error answers of every advice, to `api`."""
    for controller_class in scanned.controllers:
        mapping = scanned.mapping_of(controller_class)
        router = APIRouter(prefix=f"{API_PREFIX}{mapping.prefix}", tags=list(mapping.tags))
        for endpoint in scanned.endpoints_of(controller_class):
            router.add_api_route(
                endpoint.route_mapping.path,
                endpoint_factory.create(endpoint),
                methods=[endpoint.route_mapping.http_method],
                **_operation_options(endpoint),
            )
        api.include_router(router)
    answers: dict[type[Exception], ErrorAnswer] = {}
    for handler in scanned.error_handlers:
        answer = endpoint_factory.create_error_answer(handler)
        for error_type in handler.mapping.error_types:
            answers[error_type] = answer
            api.add_exception_handler(error_type, answer)
    _answer_invalid_requests(api, answers)


def invalid_request_of(error: RequestValidationError) -> InvalidRequestError:
    """Returns FastAPI's `RequestValidationError` in snakeboot's terms: one `RequestProblem` per error it found."""
    return InvalidRequestError(
        [
            RequestProblem(tuple(str(part) for part in problem.get("loc", ())), str(problem.get("msg", "")))
            for problem in error.errors()
        ]
    )


def _answer_invalid_requests(api: FastAPI, answers: Mapping[type[Exception], ErrorAnswer]) -> None:
    # FastAPI finds a call that does not fit before the endpoint runs, and raises its own RequestValidationError. The
    # advice that answers InvalidRequestError, or the nearest base of it, answers that too, in snakeboot's terms;
    # without one, FastAPI's own 422 stays.
    answer = next((answers[base] for base in InvalidRequestError.__mro__ if base in answers), None)
    if answer is None:
        return

    def answer_in_snakeboot_s_terms(request: Request, error: Exception) -> Response:
        if not isinstance(error, RequestValidationError):
            raise TypeError(f"Expected FastAPI's RequestValidationError, got {error!r}.")
        return answer(request, invalid_request_of(error))

    api.add_exception_handler(RequestValidationError, answer_in_snakeboot_s_terms)


def _operation_options(endpoint: DeclaredEndpoint) -> dict[str, Any]:
    # FastAPI renders the body with the response model; a stream and an empty answer have none.
    response, status = endpoint.signature.response, endpoint.route_mapping.status
    if response is ServerSentEvents:
        return {"status_code": status, "response_model": None, "response_class": EventStreamResponse}
    modelled = response is not UNDECLARED and response is not None
    return {"status_code": status, "response_model": response if modelled else None}


def _description_of(application: type) -> dict[str, Any]:
    definition = openapi_definition_of(application)
    if definition is None:
        return {}
    return {"title": definition.title, "version": definition.version, "description": definition.description}


def _health_of(application: type) -> Callable[[], dict[str, str]]:
    _, _, service = application_package(application).rpartition(".")

    def health() -> dict[str, str]:
        return {"status": "ok", "service": service}

    return health
