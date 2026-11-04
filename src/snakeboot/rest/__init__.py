"""Technical library: Spring-style singleton REST controllers on Django Ninja, wired by wireup.

    @rest_controller("/workshops", tags=["workshops"])     # @RestController + @RequestMapping
    class WorkshopRestController:
        def __init__(self, enrollment: EnrollmentFacadePort) -> None:   # constructor injection
            self._enrollment = enrollment

        @route.get("/{workshop_id}", response=WorkshopViewDTO)          # @GetMapping
        def get_workshop(self, request: HttpRequest, workshop_id: str) -> WorkshopViewDTO: ...

    @rest_controller_advice                                            # @RestControllerAdvice
    class EnrollmentRestErrorAdvice:
        @exception_handler(WorkshopNotFoundError, status=404)            # @ExceptionHandler
        def answer_not_found(self, error: Exception) -> dict[str, str]:
            return error_answer(error)

Composition adds every controller and advice in the modules of the component scan to its API:

    ControllerScan(settings.COMPONENT_SCAN).add_to(api)

It knows Django Ninja and wireup, but nothing of the application (extra: snakeboot[ninja]).
"""

from snakeboot.rest.authenticated_principal import authenticated_principal
from snakeboot.rest.controller_endpoint_factory import ControllerEndpointFactory
from snakeboot.rest.controller_scan import ControllerScan, ScannedControllers
from snakeboot.rest.error_answer import error_answer
from snakeboot.rest.rest_controller import rest_controller
from snakeboot.rest.rest_controller_advice import exception_handler, rest_controller_advice
from snakeboot.rest.rest_controller_errors import InvalidRestControllerError, NoAuthenticatedPrincipalError
from snakeboot.rest.route_markers import route

__all__ = [
    "ControllerEndpointFactory",
    "ControllerScan",
    "InvalidRestControllerError",
    "NoAuthenticatedPrincipalError",
    "ScannedControllers",
    "authenticated_principal",
    "error_answer",
    "exception_handler",
    "rest_controller",
    "rest_controller_advice",
    "route",
]
