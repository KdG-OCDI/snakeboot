from collections.abc import Callable
from typing import Any

from snakeboot.rest.file_download import is_media_type
from snakeboot.rest.rest_controller_errors import InvalidRestControllerError
from snakeboot.rest.rest_controller_mappings import ROUTE_MAPPING_ATTRIBUTE, RouteMapping

type MethodMarker = Callable[[Callable[..., Any]], Callable[..., Any]]


class RouteMarkers:
    """Marks controller methods as endpoints, like Spring's `@GetMapping` and `@PostMapping`.

    A marker only records a RouteMapping on the method; it changes nothing else. The ControllerScan reads the marks,
    and the binding of a web framework publishes them. Use the module-level instance:

        @route.get("/{workshop_id}")                            # the body is the return annotation, status 200
        def get_workshop(self, workshop_id: str) -> WorkshopViewDTO: ...

        @route.post("", status=201)                             # like @ResponseStatus(HttpStatus.CREATED)
        def create_workshop(self, body: NewWorkshopDTO) -> WorkshopViewDTO: ...

        @route.get("/{workshop_id}/summary", response=WorkshopSummaryDTO)   # a body other than the annotation
        @route.get("/open", public=True)                        # without a token, like permitAll()
        @route.get("/{workshop_id}/poster", produces="application/pdf")    # the media type of a FileDownload

    The method's name and docstring describe the endpoint in the OpenAPI document. Every option is a keyword, and
    there are no others: a misspelt option stops the start.
    """

    def get(
        self, path: str, *, response: Any = None, status: int = 200, public: bool = False, produces: str | None = None
    ) -> MethodMarker:
        """Marks a method as the handler of `GET prefix+path`."""
        return self._mark(RouteMapping("GET", path, response, status, public=public, produces=produces))

    def post(
        self, path: str, *, response: Any = None, status: int = 200, public: bool = False, produces: str | None = None
    ) -> MethodMarker:
        """Marks a method as the handler of `POST prefix+path`."""
        return self._mark(RouteMapping("POST", path, response, status, public=public, produces=produces))

    def put(
        self, path: str, *, response: Any = None, status: int = 200, public: bool = False, produces: str | None = None
    ) -> MethodMarker:
        """Marks a method as the handler of `PUT prefix+path`."""
        return self._mark(RouteMapping("PUT", path, response, status, public=public, produces=produces))

    def patch(
        self, path: str, *, response: Any = None, status: int = 200, public: bool = False, produces: str | None = None
    ) -> MethodMarker:
        """Marks a method as the handler of `PATCH prefix+path`."""
        return self._mark(RouteMapping("PATCH", path, response, status, public=public, produces=produces))

    def delete(
        self, path: str, *, response: Any = None, status: int = 200, public: bool = False, produces: str | None = None
    ) -> MethodMarker:
        """Marks a method as the handler of `DELETE prefix+path`."""
        return self._mark(RouteMapping("DELETE", path, response, status, public=public, produces=produces))

    def _mark(self, mapping: RouteMapping) -> MethodMarker:
        if mapping.produces is not None and not is_media_type(mapping.produces):
            raise InvalidRestControllerError(
                f"produces names the media type of a file, such as 'application/pdf'; got {mapping.produces!r}."
            )

        def record(method: Callable[..., Any]) -> Callable[..., Any]:
            setattr(method, ROUTE_MAPPING_ATTRIBUTE, mapping)
            return method

        return record


route = RouteMarkers()
