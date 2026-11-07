import inspect
from collections.abc import Sequence
from dataclasses import dataclass

from ninja import NinjaAPI, Router

from snakeboot.component_scan import ComponentScan
from snakeboot.rest.controller_endpoint_factory import ControllerEndpointFactory
from snakeboot.rest.rest_controller_errors import InvalidRestControllerError
from snakeboot.rest.rest_controller_mappings import (
    ADVICE_MARKER_ATTRIBUTE,
    CONTROLLER_MAPPING_ATTRIBUTE,
    EXCEPTION_HANDLER_ATTRIBUTE,
    ROUTE_MAPPING_ATTRIBUTE,
    ControllerMapping,
    DeclaredEndpoint,
    ExceptionHandlerMapping,
)


@dataclass(frozen=True, slots=True)
class ScannedControllers:
    """What ControllerScan added to an API: the controllers and the advices it found."""

    controllers: list[type]
    advices: list[type]


class ControllerScan:
    """Finds the controllers and advices in the modules of the component scan and adds them to a Ninja API.

    Like Spring, where the component scan finds every `@RestController` and its request mappings become routes:
    the scan that fills the container also gives the API its routes, so a controller the container knows always
    has its routes, and the other way round.

        ControllerScan(settings.COMPONENT_SCAN).add_to(api)

    Like Spring, it refuses to start on an ambiguous mapping: two endpoints for the same HTTP method and path, or
    two advice methods for the same error type.
    """

    def __init__(
        self, component_scan: ComponentScan, endpoint_factory: ControllerEndpointFactory | None = None
    ) -> None:
        self._component_scan = component_scan
        self._endpoint_factory = endpoint_factory or ControllerEndpointFactory()

    def add_to(self, api: NinjaAPI) -> ScannedControllers:
        """Adds one router per controller and the error answers of every advice to `api`."""
        controllers = self._component_scan.classes_marked(CONTROLLER_MAPPING_ATTRIBUTE)
        advices = self._component_scan.classes_marked(ADVICE_MARKER_ATTRIBUTE)
        endpoints_by_controller = {controller: self._endpoints_of(controller) for controller in controllers}
        self._refuse_ambiguous_routes([e for endpoints in endpoints_by_controller.values() for e in endpoints])
        for controller_class, endpoints in endpoints_by_controller.items():
            prefix = self._controller_mapping(controller_class).prefix
            api.add_router(prefix, self._router_for(controller_class, endpoints))
        self._register_error_answers(api, advices)
        return ScannedControllers(controllers=controllers, advices=advices)

    def _controller_mapping(self, controller_class: type) -> ControllerMapping:
        mapping: ControllerMapping = getattr(controller_class, CONTROLLER_MAPPING_ATTRIBUTE)
        return mapping

    def _endpoints_of(self, controller_class: type) -> list[DeclaredEndpoint]:
        prefix = self._controller_mapping(controller_class).prefix
        endpoints = [
            DeclaredEndpoint(controller_class, method, prefix, route_mapping)
            for _, method in inspect.getmembers(controller_class, inspect.isfunction)
            if (route_mapping := getattr(method, ROUTE_MAPPING_ATTRIBUTE, None)) is not None
        ]
        if not endpoints:
            raise InvalidRestControllerError(f"{controller_class.__name__} has no @route methods.")
        return endpoints

    def _refuse_ambiguous_routes(self, endpoints: Sequence[DeclaredEndpoint]) -> None:
        claimed: dict[tuple[str, str], DeclaredEndpoint] = {}
        for endpoint in endpoints:
            if (earlier := claimed.get(endpoint.route_key)) is not None:
                http_method, path = endpoint.route_key
                raise InvalidRestControllerError(
                    f"Ambiguous mapping: {http_method} '{path}' is mapped by {earlier.name} and {endpoint.name}."
                )
            claimed[endpoint.route_key] = endpoint

    def _router_for(self, controller_class: type, endpoints: Sequence[DeclaredEndpoint]) -> Router:
        router = Router(tags=list(self._controller_mapping(controller_class).tags))
        for endpoint in endpoints:
            router.add_api_operation(
                endpoint.route_mapping.path,
                [endpoint.route_mapping.http_method],
                self._endpoint_factory.create(controller_class, endpoint.method),
                **endpoint.route_mapping.options,
            )
        return router

    def _register_error_answers(self, api: NinjaAPI, advices: Sequence[type]) -> None:
        answered_by: dict[type[Exception], str] = {}
        for advice_class in advices:
            for _, method in inspect.getmembers(advice_class, inspect.isfunction):
                mapping: ExceptionHandlerMapping | None = getattr(method, EXCEPTION_HANDLER_ATTRIBUTE, None)
                if mapping is None:
                    continue
                answer = self._endpoint_factory.create_error_answer(
                    advice_class, method, api=api, status=mapping.status
                )
                for error_type in mapping.error_types:
                    self._claim_error_type(answered_by, error_type, f"{advice_class.__name__}.{method.__name__}")
                    # Ninja annotates the handler's error as `Exception | type[Exception]`, but passes an instance.
                    api.add_exception_handler(error_type, answer)  # type: ignore[arg-type]

    def _claim_error_type(self, answered_by: dict[type[Exception], str], error_type: type[Exception], by: str) -> None:
        if (earlier := answered_by.get(error_type)) is not None:
            raise InvalidRestControllerError(
                f"Ambiguous mapping: {error_type.__name__} is answered by {earlier} and {by}."
            )
        answered_by[error_type] = by
