import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from snakeboot.rest.endpoint_signature import EndpointSignature

CONTROLLER_MAPPING_ATTRIBUTE: Final = "__rest_controller_mapping__"
ROUTE_MAPPING_ATTRIBUTE: Final = "__rest_route_mapping__"
ADVICE_MARKER_ATTRIBUTE: Final = "__rest_controller_advice__"
EXCEPTION_HANDLER_ATTRIBUTE: Final = "__rest_exception_handler_mapping__"

_PATH_PARAMETER: Final = re.compile(r"\{[^}]*\}")
_PATH_PARAMETER_NAME: Final = re.compile(r"\{([^}:]*)")
"""The name in `{name}`, also before the converter of `{name:path}`."""


@dataclass(frozen=True, slots=True)
class ControllerMapping:
    """What `@rest_controller` records on a class: the URL prefix and the OpenAPI tags."""

    prefix: str
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RouteMapping:
    """What `@route.get(...)` and friends record on a method: the HTTP method, the path and how it answers.

    `response` is the type of the body when it differs from the return annotation (None: take the annotation),
    `status` the status of a successful answer, `public` whether the endpoint answers without authentication, and
    `produces` the media type of the `FileDownload` it answers with, for the OpenAPI document (None: any).
    Nothing here names a web framework, so any binding can publish the route.
    """

    http_method: str
    path: str
    response: Any = None
    status: int = 200
    public: bool = False
    produces: str | None = None


@dataclass(frozen=True, slots=True)
class ExceptionHandlerMapping:
    """What `@exception_handler(...)` records on an advice method: the errors it answers and the status."""

    error_types: tuple[type[Exception], ...]
    status: int


@dataclass(frozen=True, slots=True)
class DeclaredEndpoint:
    """One `@route` method of one controller, read and checked, as a binding is about to publish it.

    `roles` are the roles of which a caller needs one (`@roles_allowed`); empty, any authenticated caller will do.
    """

    controller_class: type
    method: Callable[..., Any]
    prefix: str
    route_mapping: RouteMapping
    signature: EndpointSignature
    roles: frozenset[str] = frozenset()

    @property
    def name(self) -> str:
        """`Controller.method`, for error messages."""
        return f"{self.controller_class.__name__}.{self.method.__name__}"

    @property
    def path_parameters(self) -> frozenset[str]:
        """The names of the parameters that the path holds: `workshop_id` of `{workshop_id}`, in the prefix or not."""
        return frozenset(_PATH_PARAMETER_NAME.findall(f"{self.prefix}/{self.route_mapping.path}"))

    @property
    def route_key(self) -> tuple[str, str]:
        """HTTP method and full path, with every path parameter reduced to `{}`.

        `/workshops/{workshop_id}` and `/workshops/{id}` match the same URLs, so they get
        the same key: like Spring, two endpoints with one key are an ambiguous mapping.
        """
        segments = [segment for segment in f"{self.prefix}/{self.route_mapping.path}".split("/") if segment]
        return self.route_mapping.http_method, _PATH_PARAMETER.sub("{}", "/" + "/".join(segments))


@dataclass(frozen=True, slots=True)
class DeclaredErrorHandler:
    """One `@exception_handler` method of one advice: the method that builds the body, and what it answers."""

    advice_class: type
    method: Callable[..., Any]
    mapping: ExceptionHandlerMapping

    @property
    def name(self) -> str:
        """`Advice.method`, for error messages."""
        return f"{self.advice_class.__name__}.{self.method.__name__}"
