import inspect
from collections.abc import Sequence
from dataclasses import dataclass

from snakeboot.component_scan import ComponentScan
from snakeboot.rest.bearer_authentication import AUTHENTICATION_MARKER_ATTRIBUTE, BearerAuthentication
from snakeboot.rest.endpoint_signature import EndpointSignature, method_parameters
from snakeboot.rest.rest_controller_errors import InvalidRestControllerError
from snakeboot.rest.rest_controller_mappings import (
    ADVICE_MARKER_ATTRIBUTE,
    CONTROLLER_MAPPING_ATTRIBUTE,
    EXCEPTION_HANDLER_ATTRIBUTE,
    ROUTE_MAPPING_ATTRIBUTE,
    ControllerMapping,
    DeclaredEndpoint,
    DeclaredErrorHandler,
    ExceptionHandlerMapping,
    RouteMapping,
)


@dataclass(frozen=True, slots=True)
class ScannedControllers:
    """The REST API that a component scan declares, checked and ready for the binding of a web framework.

    The controllers and advices in the order of their modules, every endpoint and error answer they declare, and
    the `BearerAuthentication` of the API, or None for an API without authentication.
    """

    controllers: list[type]
    advices: list[type]
    endpoints: list[DeclaredEndpoint]
    error_handlers: list[DeclaredErrorHandler]
    authentication: type[BearerAuthentication] | None

    def mapping_of(self, controller_class: type) -> ControllerMapping:
        """The prefix and the OpenAPI tags of `controller_class`."""
        mapping: ControllerMapping = getattr(controller_class, CONTROLLER_MAPPING_ATTRIBUTE)
        return mapping

    def endpoints_of(self, controller_class: type) -> list[DeclaredEndpoint]:
        """The endpoints of `controller_class`, in the order of their method names."""
        return [endpoint for endpoint in self.endpoints if endpoint.controller_class is controller_class]


class ControllerScan:
    """Finds the controllers, advices and authentication of the REST API in the modules of the component scan.

    Like Spring, where the component scan finds every `@RestController` and its request mappings become routes:
    the scan that fills the container also declares the API, so a controller the container knows always has its
    routes, and the other way round. It knows no web framework; a binding publishes what it finds.

        scanned = ControllerScan(ComponentScan.of(MyApplication)).find()

    Like Spring, it refuses to start on an ambiguous API: two endpoints for the same HTTP method and path, two
    advice methods for the same error type, or two authentications. An endpoint that asks for a `Principal` while
    nobody authenticates its calls stops the start too.
    """

    def __init__(self, component_scan: ComponentScan) -> None:
        self._component_scan = component_scan

    def find(self) -> ScannedControllers:
        """Returns the API the component scan declares, after checking it."""
        controllers = self._component_scan.classes_marked(CONTROLLER_MAPPING_ATTRIBUTE)
        advices = self._component_scan.classes_marked(ADVICE_MARKER_ATTRIBUTE)
        endpoints = [endpoint for controller in controllers for endpoint in self._endpoints_of(controller)]
        authentication = self._authentication()
        _refuse_ambiguous_routes(endpoints)
        _refuse_principals_nobody_supplies(endpoints, authenticated=authentication is not None)
        error_handlers = [handler for advice in advices for handler in self._error_handlers_of(advice)]
        _refuse_ambiguous_error_handlers(error_handlers)
        return ScannedControllers(controllers, advices, endpoints, error_handlers, authentication)

    def _endpoints_of(self, controller_class: type) -> list[DeclaredEndpoint]:
        mapping: ControllerMapping = getattr(controller_class, CONTROLLER_MAPPING_ATTRIBUTE)
        endpoints = [
            DeclaredEndpoint(
                controller_class,
                method,
                mapping.prefix,
                route_mapping,
                EndpointSignature.of(controller_class, method, route_mapping.response),
            )
            for _, method in inspect.getmembers(controller_class, inspect.isfunction)
            if isinstance(route_mapping := getattr(method, ROUTE_MAPPING_ATTRIBUTE, None), RouteMapping)
        ]
        if not endpoints:
            raise InvalidRestControllerError(f"{controller_class.__name__} has no @route methods.")
        return endpoints

    def _error_handlers_of(self, advice_class: type) -> list[DeclaredErrorHandler]:
        handlers = [
            DeclaredErrorHandler(advice_class, method, mapping)
            for _, method in inspect.getmembers(advice_class, inspect.isfunction)
            if isinstance(mapping := getattr(method, EXCEPTION_HANDLER_ATTRIBUTE, None), ExceptionHandlerMapping)
        ]
        for handler in handlers:
            method_parameters(advice_class, handler.method)
        return handlers

    def _authentication(self) -> type[BearerAuthentication] | None:
        declared = [
            candidate
            for candidate in self._component_scan.classes_marked(AUTHENTICATION_MARKER_ATTRIBUTE)
            if issubclass(candidate, BearerAuthentication)
        ]
        if len(declared) > 1:
            names = ", ".join(f"{cls.__module__}.{cls.__qualname__}" for cls in declared)
            raise InvalidRestControllerError(
                f"The API has one BearerAuthentication, the component scan declares {names}."
            )
        return declared[0] if declared else None


def _refuse_ambiguous_routes(endpoints: Sequence[DeclaredEndpoint]) -> None:
    claimed: dict[tuple[str, str], DeclaredEndpoint] = {}
    for endpoint in endpoints:
        if (earlier := claimed.get(endpoint.route_key)) is not None:
            http_method, path = endpoint.route_key
            raise InvalidRestControllerError(
                f"Ambiguous mapping: {http_method} '{path}' is mapped by {earlier.name} and {endpoint.name}."
            )
        claimed[endpoint.route_key] = endpoint


def _refuse_principals_nobody_supplies(endpoints: Sequence[DeclaredEndpoint], *, authenticated: bool) -> None:
    for endpoint in endpoints:
        if not endpoint.signature.principal_parameters:
            continue
        if endpoint.route_mapping.public:
            raise InvalidRestControllerError(
                f"{endpoint.name} is public, so nobody is authenticated: it cannot ask for a Principal."
            )
        if not authenticated:
            raise InvalidRestControllerError(
                f"{endpoint.name} asks for a Principal, but the component scan declares no BearerAuthentication."
            )


def _refuse_ambiguous_error_handlers(handlers: Sequence[DeclaredErrorHandler]) -> None:
    answered_by: dict[type[Exception], DeclaredErrorHandler] = {}
    for handler in handlers:
        for error_type in handler.mapping.error_types:
            if (earlier := answered_by.get(error_type)) is not None:
                raise InvalidRestControllerError(
                    f"Ambiguous mapping: {error_type.__name__} is answered by {earlier.name} and {handler.name}."
                )
            answered_by[error_type] = handler
