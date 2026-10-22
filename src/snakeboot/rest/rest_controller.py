from collections.abc import Callable, Sequence

from wireup import injectable

from snakeboot.rest.rest_controller_errors import InvalidRestControllerError
from snakeboot.rest.rest_controller_mappings import CONTROLLER_MAPPING_ATTRIBUTE, ControllerMapping


def rest_controller[C: type](prefix: str, *, tags: Sequence[str] = ()) -> Callable[[C], C]:
    """Declares a REST controller, like Spring's `@RestController` with `@RequestMapping(prefix)`.

    The class becomes a wireup singleton (do not add `@injectable` yourself): its
    constructor receives facade ports by type, it is created once, and the container
    refuses to start when a dependency is missing. RestControllerMounter finds it by
    scanning and turns its `@route` methods into Ninja endpoints under `prefix`.
    """
    if prefix != "" and not prefix.startswith("/"):
        raise InvalidRestControllerError(f"A controller prefix starts with '/', got {prefix!r}.")

    def declare(controller_class: C) -> C:
        mapping = ControllerMapping(prefix=prefix, tags=tuple(tags) or (controller_class.__name__,))
        setattr(controller_class, CONTROLLER_MAPPING_ATTRIBUTE, mapping)
        return injectable(controller_class)

    return declare
