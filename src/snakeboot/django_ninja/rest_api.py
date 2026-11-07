from collections.abc import Callable
from typing import Any, Final, override

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, JsonResponse
from django.urls import URLPattern, URLResolver, path
from ninja import NinjaAPI, Router
from ninja.constants import NOT_SET
from ninja.security import HttpBearer

from snakeboot.component_scan import ComponentScan, application_package
from snakeboot.django_ninja.ninja_endpoint_factory import (
    ComponentResolver,
    NinjaEndpointFactory,
    resolve_from_wireup_request_scope,
)
from snakeboot.openapi import openapi_definition_of
from snakeboot.rest import UNDECLARED, BearerAuthentication, ControllerScan, DeclaredEndpoint, ScannedControllers

NINJA_DEFAULT_STATUS: Final = 200
"""The status of an operation that names no response: then Ninja needs to be told nothing."""


def rest_api(application: type, resolve: ComponentResolver = resolve_from_wireup_request_scope) -> NinjaAPI:
    """Returns the REST API of `application` on Django Ninja: every controller and advice of its component scan.

    The title, version and description come from `@openapi_definition` on the application class; without it, the
    API has Django Ninja's defaults. When the component scan holds a `BearerAuthentication`, every endpoint that is
    not public asks it for the bearer token. `resolve` finds a component for a call; tests give a container's `get`.
    """
    scanned = ControllerScan(ComponentScan.of(application)).find()
    arguments = _description_of(application)
    if scanned.authentication is not None:
        arguments["auth"] = BearerToken(resolve)
    api = NinjaAPI(**arguments)
    add_routes(api, scanned, NinjaEndpointFactory(resolve))
    return api


def add_routes(api: NinjaAPI, scanned: ScannedControllers, endpoint_factory: NinjaEndpointFactory) -> None:
    """Adds one router per controller, and the error answers of every advice, to `api`."""
    for controller_class in scanned.controllers:
        mapping = scanned.mapping_of(controller_class)
        router = Router(tags=list(mapping.tags))
        for endpoint in scanned.endpoints_of(controller_class):
            router.add_api_operation(
                endpoint.route_mapping.path,
                [endpoint.route_mapping.http_method],
                endpoint_factory.create(endpoint),
                **_operation_options(endpoint),
            )
        api.add_router(mapping.prefix, router)
    for handler in scanned.error_handlers:
        answer = endpoint_factory.create_error_answer(handler, api)
        for error_type in handler.mapping.error_types:
            # Ninja annotates the handler's error as `Exception | type[Exception]`, but passes an instance.
            api.add_exception_handler(error_type, answer)  # type: ignore[arg-type]


def url_patterns(application: type) -> list[URLPattern | URLResolver]:
    """Returns the URLs of `application`: its REST API under /api/ and a liveness probe at /health.

    /health is a plain Django view, outside the API, so it answers without authentication: Docker and the platform
    ask it whether the service runs.
    """
    return [path("api/", rest_api(application).urls), path("health", _health_of(application))]


class BearerToken(HttpBearer):
    """Ninja's authentication of the API: it asks the container's `BearerAuthentication`, once per call."""

    def __init__(self, resolve: ComponentResolver) -> None:
        super().__init__()
        self._resolve = resolve

    @override
    def authenticate(self, request: HttpRequest, token: str) -> str | None:
        authentication = self._resolve(BearerAuthentication)
        if not isinstance(authentication, BearerAuthentication):
            raise ImproperlyConfigured(f"The container gave {authentication!r} as the BearerAuthentication.")
        return authentication.authenticate(token)


def _operation_options(endpoint: DeclaredEndpoint) -> dict[str, Any]:
    # Ninja answers with the status of the one response it knows, so the method returns the body only.
    mapping, response = endpoint.route_mapping, endpoint.signature.response
    options: dict[str, Any] = {}
    if response is not UNDECLARED or mapping.status != NINJA_DEFAULT_STATUS:
        options["response"] = {mapping.status: NOT_SET if response is UNDECLARED else response}
    if mapping.public:
        options["auth"] = None
    return options


def _description_of(application: type) -> dict[str, Any]:
    definition = openapi_definition_of(application)
    if definition is None:
        return {}
    return {"title": definition.title, "version": definition.version, "description": definition.description}


def _health_of(application: type) -> Callable[[HttpRequest], JsonResponse]:
    _, _, service = application_package(application).rpartition(".")

    def health(_request: HttpRequest) -> JsonResponse:
        return JsonResponse({"status": "ok", "service": service})

    return health
