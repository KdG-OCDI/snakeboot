import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Final

CONTROLLER_MAPPING_ATTRIBUTE: Final = "__rest_controller_mapping__"
ROUTE_MAPPING_ATTRIBUTE: Final = "__rest_route_mapping__"
ADVICE_MARKER_ATTRIBUTE: Final = "__rest_controller_advice__"
EXCEPTION_HANDLER_ATTRIBUTE: Final = "__rest_exception_handler_mapping__"

_PATH_PARAMETER: Final = re.compile(r"\{[^}]*\}")


@dataclass(frozen=True, slots=True)
class ControllerMapping:
    """What `@rest_controller` records on a class: the URL prefix and the OpenAPI tags."""

    prefix: str
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RouteMapping:
    """What `@route.get(...)` and friends record on a method: HTTP method, path and Ninja options.

    The options are passed to Ninja unchanged (`response`, `auth`, `summary`, ...).
    """

    http_method: str
    path: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExceptionHandlerMapping:
    """What `@exception_handler(...)` records on an advice method: the errors it answers and the status."""

    error_types: tuple[type[Exception], ...]
    status: int


@dataclass(frozen=True, slots=True)
class DeclaredEndpoint:
    """One `@route` method of one controller, as the mounter is about to publish it."""

    controller_class: type
    method: Callable[..., Any]
    prefix: str
    route_mapping: RouteMapping

    @property
    def name(self) -> str:
        """`Controller.method`, for error messages."""
        return f"{self.controller_class.__name__}.{self.method.__name__}"

    @property
    def route_key(self) -> tuple[str, str]:
        """HTTP method and full path, with every path parameter reduced to `{}`.

        `/workshops/{workshop_id}` and `/workshops/{id}` match the same URLs, so they get
        the same key: like Spring, two endpoints with one key are an ambiguous mapping.
        """
        segments = [segment for segment in f"{self.prefix}/{self.route_mapping.path}".split("/") if segment]
        return self.route_mapping.http_method, _PATH_PARAMETER.sub("{}", "/" + "/".join(segments))
