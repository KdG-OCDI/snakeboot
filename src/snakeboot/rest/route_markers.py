from collections.abc import Callable
from typing import Any

from snakeboot.rest.rest_controller_mappings import ROUTE_MAPPING_ATTRIBUTE, RouteMapping


class RouteMarkers:
    """Marks controller methods as endpoints, like Spring's `@GetMapping` and `@PostMapping`.

    A marker only records a RouteMapping on the method; it changes nothing else. The
    RestControllerMounter reads the marks when it builds the Ninja routers. Use the
    module-level instance: `@route.get("/{workshop_id}", response=WorkshopViewDTO)`.
    """

    def get(self, path: str, **options: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Marks a method as the handler of `GET prefix+path`."""
        return self._mark("GET", path, options)

    def post(self, path: str, **options: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Marks a method as the handler of `POST prefix+path`."""
        return self._mark("POST", path, options)

    def put(self, path: str, **options: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Marks a method as the handler of `PUT prefix+path`."""
        return self._mark("PUT", path, options)

    def patch(self, path: str, **options: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Marks a method as the handler of `PATCH prefix+path`."""
        return self._mark("PATCH", path, options)

    def delete(self, path: str, **options: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Marks a method as the handler of `DELETE prefix+path`."""
        return self._mark("DELETE", path, options)

    def _mark(
        self, http_method: str, path: str, options: dict[str, Any]
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def record(method: Callable[..., Any]) -> Callable[..., Any]:
            setattr(method, ROUTE_MAPPING_ATTRIBUTE, RouteMapping(http_method, path, options))
            return method

        return record


route = RouteMarkers()
