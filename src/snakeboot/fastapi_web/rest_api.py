from collections.abc import Mapping
from typing import Any, Final

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse, Response

from snakeboot.actuator import Actuator
from snakeboot.component_scan import ComponentScan, application_package
from snakeboot.configuration import CorsProperties, ServerProperties
from snakeboot.fastapi_web.actuator_endpoints import add_actuator
from snakeboot.fastapi_web.bearer_token import BearerToken, ComponentResolver
from snakeboot.fastapi_web.event_stream import EventStreamResponse
from snakeboot.fastapi_web.fastapi_endpoint_factory import ErrorAnswer, FastApiEndpointFactory
from snakeboot.fastapi_web.file_download_response import file_download_documentation
from snakeboot.fastapi_web.observation import RequestMetricsMiddleware, TracingMiddleware
from snakeboot.openapi import openapi_definition_of
from snakeboot.rest import (
    DEFAULT_MAX_UPLOAD_SIZE,
    UNDECLARED,
    ControllerScan,
    DeclaredEndpoint,
    FileDownload,
    InvalidRequestError,
    RequestProblem,
    ScannedControllers,
    ServerSentEvents,
    UploadTooLargeError,
    error_answer,
)

API_PREFIX: Final = "/api"
"""Where the REST API lives; its OpenAPI document is /api/openapi.json and Swagger UI /api/docs."""

EXPOSED_HEADERS: Final = ("Content-Disposition",)
"""What the script of a page of another origin may read of an answer, beyond what CORS always lets it read.

A page that downloads a file with `fetch` (to send its bearer token) reads the file name in `Content-Disposition`.
"""

CONTENT_TOO_LARGE: Final = 413
"""The status of an upload larger than the server takes, without an advice for it (RFC 9110's Content Too Large)."""


def rest_api(
    application: type,
    resolve: ComponentResolver,
    *,
    server: ServerProperties | None = None,
    cors: CorsProperties | None = None,
    actuator: Actuator | None = None,
) -> FastAPI:
    """Returns the REST API of `application` on FastAPI: every controller and advice of its component scan.

    The title, version and description come from `@openapi_definition` on the application class. When the component
    scan holds a `BearerAuthentication`, every endpoint that is not public asks it for the bearer token. `server`
    turns on FastAPI's debug answers, accepts only its `allowed_hosts` and takes uploaded files of up to its
    `max_upload_size`; without it, as in a test, every host is accepted and a file of up to 1 MiB. `cors` names the
    origins whose pages may call the API, and whose scripts may read the file name of a `FileDownload`. `resolve`
    finds a component for a call: the container's `get`, or a test's.

    Beside the API it serves the health and the metrics of `actuator` (`/health`, `/health/liveness`,
    `/health/readiness`, `/metrics`), runs every call in a span of its trace, and times it.
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
    add_routes(api, scanned, FastApiEndpointFactory(resolve, bearer_token, max_upload_size=_max_upload_size(server)))
    observed = actuator or Actuator()
    add_actuator(api, application_package(application).rpartition(".")[2], observed)
    # Starlette runs the middleware added last first: the timing sees every answer, the span every log line.
    if server is not None:
        api.add_middleware(TrustedHostMiddleware, allowed_hosts=list(server.allowed_hosts))
    if cors is not None:
        api.add_middleware(
            CORSMiddleware,
            allow_origins=list(cors.allowed_origins),
            allow_methods=list(cors.allowed_methods),
            allow_headers=list(cors.allowed_headers),
            allow_credentials=cors.allow_credentials,
            expose_headers=list(EXPOSED_HEADERS),
        )
    api.add_middleware(TracingMiddleware)
    api.add_middleware(RequestMetricsMiddleware, meters=observed.meters)
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
    _answer_uploads_too_large(api, answers)


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


def _answer_uploads_too_large(api: FastAPI, answers: Mapping[type[Exception], ErrorAnswer]) -> None:
    # The advice that answers UploadTooLargeError, or the nearest base of it, answers it; without one, the API answers
    # 413 in snakeboot's words, as a file too large is the client's error and not the server's 500.
    if any(base in answers for base in UploadTooLargeError.__mro__):
        return

    def answer_content_too_large(_request: Request, error: Exception) -> Response:
        return JSONResponse(error_answer(error), status_code=CONTENT_TOO_LARGE)

    api.add_exception_handler(UploadTooLargeError, answer_content_too_large)


def _max_upload_size(server: ServerProperties | None) -> int:
    if server is None or server.max_upload_size is None:
        return DEFAULT_MAX_UPLOAD_SIZE
    return server.max_upload_size


def _operation_options(endpoint: DeclaredEndpoint) -> dict[str, Any]:
    # FastAPI renders the body with the response model; a stream, a file and an empty answer have none.
    response, status = endpoint.signature.response, endpoint.route_mapping.status
    if response is ServerSentEvents:
        return {"status_code": status, "response_model": None, "response_class": EventStreamResponse}
    if response is FileDownload:
        return {
            "status_code": status,
            "response_model": None,
            "response_class": Response,
            "responses": file_download_documentation(endpoint),
        }
    modelled = response is not UNDECLARED and response is not None
    return {"status_code": status, "response_model": response if modelled else None}


def _description_of(application: type) -> dict[str, Any]:
    definition = openapi_definition_of(application)
    if definition is None:
        return {}
    return {"title": definition.title, "version": definition.version, "description": definition.description}
