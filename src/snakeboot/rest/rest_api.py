import importlib
from collections.abc import Callable
from typing import Any, override

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, JsonResponse
from django.urls import URLPattern, URLResolver, path
from ninja import NinjaAPI
from ninja.security import HttpBearer

from snakeboot.component_scan import ComponentScan, application_package
from snakeboot.openapi import openapi_definition_of
from snakeboot.rest.bearer_authentication import BearerAuthentication
from snakeboot.rest.controller_endpoint_factory import (
    ControllerEndpointFactory,
    ControllerResolver,
    resolve_from_wireup_request_scope,
)
from snakeboot.rest.controller_scan import ControllerScan


def rest_api(application: type, resolve: ControllerResolver = resolve_from_wireup_request_scope) -> NinjaAPI:
    """Returns the REST API of `application`: every controller and advice of its component scan.

    The title, version and description come from `@openapi_definition` on the application class; without it, the
    API has Django Ninja's defaults. When the component scan holds a `BearerAuthentication`, every endpoint asks it
    for the bearer token. `resolve` finds a component for a call; tests give a container's `get`.
    """
    scan = ComponentScan.of(application)
    arguments = _description_of(application)
    if _declares_bearer_authentication(scan):
        arguments["auth"] = BearerToken(resolve)
    api = NinjaAPI(**arguments)
    ControllerScan(scan, ControllerEndpointFactory(resolve)).add_to(api)
    return api


def url_patterns(application: type) -> list[URLPattern | URLResolver]:
    """Returns the URLs of `application`: its REST API under /api/ and a liveness probe at /health.

    /health is a plain Django view, outside the API, so it answers without authentication: Docker and the platform
    ask it whether the service runs.
    """
    return [path("api/", rest_api(application).urls), path("health", _health_of(application))]


class BearerToken(HttpBearer):
    """Ninja's authentication of the API: it asks the container's `BearerAuthentication`, once per call."""

    def __init__(self, resolve: ControllerResolver) -> None:
        super().__init__()
        self._resolve = resolve

    @override
    def authenticate(self, request: HttpRequest, token: str) -> str | None:
        authentication = self._resolve(BearerAuthentication)
        if not isinstance(authentication, BearerAuthentication):
            raise ImproperlyConfigured(f"The container gave {authentication!r} as the BearerAuthentication.")
        return authentication.authenticate(token)


def _description_of(application: type) -> dict[str, Any]:
    definition = openapi_definition_of(application)
    if definition is None:
        return {}
    return {"title": definition.title, "version": definition.version, "description": definition.description}


def _declares_bearer_authentication(scan: ComponentScan) -> bool:
    declared = [
        candidate
        for name in scan.module_names()
        for candidate in vars(importlib.import_module(name)).values()
        if isinstance(candidate, type)
        and issubclass(candidate, BearerAuthentication)
        and candidate is not BearerAuthentication
        and candidate.__module__ == name
    ]
    if len(declared) > 1:
        names = ", ".join(sorted(f"{cls.__module__}.{cls.__qualname__}" for cls in declared))
        raise ImproperlyConfigured(f"The API has one BearerAuthentication, the component scan declares {names}.")
    return bool(declared)


def _health_of(application: type) -> Callable[[HttpRequest], JsonResponse]:
    _, _, service = application_package(application).rpartition(".")

    def health(_request: HttpRequest) -> JsonResponse:
        return JsonResponse({"status": "ok", "service": service})

    return health
