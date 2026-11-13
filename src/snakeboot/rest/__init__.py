"""Technical library: Spring-style singleton REST controllers, wired by wireup, in no web framework's terms.

    @rest_controller("/workshops", tags=["workshops"])     # @RestController + @RequestMapping
    class WorkshopRestController:
        def __init__(self, enrollment: EnrollmentFacadePort) -> None:   # constructor injection
            self._enrollment = enrollment

        @route.get("/{workshop_id}")                                    # @GetMapping
        def get_workshop(self, workshop_id: str) -> WorkshopViewDTO: ...

        @route.post("/{workshop_id}/registrations", status=201)         # @PostMapping + @ResponseStatus(CREATED)
        def register(self, workshop_id: str, participant: Principal) -> RegistrationDTO: ...

        @route.delete("/{workshop_id}")
        @roles_allowed("organizer")                                     # @RolesAllowed("organizer")
        def cancel(self, workshop_id: str) -> None: ...

        @route.get("/{workshop_id}/events")                             # SseEmitter, Flux<ServerSentEvent>
        def watch(self, workshop_id: str) -> ServerSentEvents: ...

        @route.post("/{workshop_id}/handouts", status=201)              # @RequestPart MultipartFile
        def add_handout(self, workshop_id: str, handout: UploadedFile, title: str) -> HandoutDTO: ...

        @route.get("/{workshop_id}/handouts/{handout_id}")              # ResponseEntity<Resource>
        def download_handout(self, workshop_id: str, handout_id: str) -> FileDownload: ...

    @rest_controller_advice                                            # @RestControllerAdvice
    class EnrollmentRestErrorAdvice:
        @exception_handler(WorkshopNotFoundError, status=404)            # @ExceptionHandler
        def answer_not_found(self, error: Exception) -> dict[str, str]:
            return error_answer(error)

A controller sees no request and no response object: it takes what the call carries (path, query and body
parameters, the body as a Pydantic model, or an `UploadedFile` and the other fields of its form) and a `Principal`,
and returns the body, `ServerSentEvents` to stream or a `FileDownload` to answer with a file.
`@roles_allowed` on an endpoint or a controller answers 403 to a caller without one of its roles.
`ControllerScan` finds every controller, advice and `BearerAuthentication` of the component scan and checks them;
the binding of a web framework (`snakeboot.fastapi_web`, today) publishes them, so another binding changes no
controller.

It knows wireup, the component scan, `snakeboot.security` and Pydantic's JSON, but no web framework and nothing of
the application.
"""

from snakeboot.rest.bearer_authentication import BearerAuthentication
from snakeboot.rest.controller_scan import ControllerScan, ScannedControllers
from snakeboot.rest.endpoint_signature import UNDECLARED, EndpointSignature
from snakeboot.rest.error_answer import error_answer
from snakeboot.rest.file_download import FileDownload
from snakeboot.rest.invalid_request_error import InvalidRequestError, RequestProblem
from snakeboot.rest.principal import Principal
from snakeboot.rest.rest_controller import rest_controller
from snakeboot.rest.rest_controller_advice import exception_handler, rest_controller_advice
from snakeboot.rest.rest_controller_errors import InvalidRestControllerError, NoAuthenticatedPrincipalError
from snakeboot.rest.rest_controller_mappings import DeclaredEndpoint, DeclaredErrorHandler, RouteMapping
from snakeboot.rest.roles_allowed import roles_allowed
from snakeboot.rest.route_markers import route
from snakeboot.rest.server_sent_events import BlockingRunner, ServerSentEvent, ServerSentEvents
from snakeboot.rest.uploaded_file import (
    DEFAULT_MAX_UPLOAD_SIZE,
    UNNAMED_CONTENT_TYPE,
    UploadedFile,
    UploadTooLargeError,
)

__all__ = [
    "DEFAULT_MAX_UPLOAD_SIZE",
    "UNDECLARED",
    "UNNAMED_CONTENT_TYPE",
    "BearerAuthentication",
    "BlockingRunner",
    "ControllerScan",
    "DeclaredEndpoint",
    "DeclaredErrorHandler",
    "EndpointSignature",
    "FileDownload",
    "InvalidRequestError",
    "InvalidRestControllerError",
    "NoAuthenticatedPrincipalError",
    "Principal",
    "RequestProblem",
    "RouteMapping",
    "ScannedControllers",
    "ServerSentEvent",
    "ServerSentEvents",
    "UploadTooLargeError",
    "UploadedFile",
    "error_answer",
    "exception_handler",
    "rest_controller",
    "rest_controller_advice",
    "roles_allowed",
    "route",
]
