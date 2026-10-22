from collections.abc import Callable
from typing import Any

from wireup import injectable

from snakeboot.rest.rest_controller_errors import InvalidRestControllerError
from snakeboot.rest.rest_controller_mappings import (
    ADVICE_MARKER_ATTRIBUTE,
    EXCEPTION_HANDLER_ATTRIBUTE,
    ExceptionHandlerMapping,
)


def rest_controller_advice[C: type](advice_class: C) -> C:
    """Declares how errors become HTTP answers for every controller, like Spring's `@RestControllerAdvice`.

    The class becomes a wireup singleton, like a controller. RestControllerMounter finds it
    with the same component scan and registers each `@exception_handler` method with Ninja,
    so composition never lists an error translation.
    """
    setattr(advice_class, ADVICE_MARKER_ATTRIBUTE, True)
    return injectable(advice_class)


def exception_handler(*error_types: type[Exception], status: int) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Marks an advice method as the answer to `error_types`, like Spring's `@ExceptionHandler`.

    The method receives the error and returns the body; the answer gets `status`.
    Ninja picks the most specific error type through the class hierarchy.
    """
    if not error_types:
        raise InvalidRestControllerError("@exception_handler needs at least one error type.")

    def record(method: Callable[..., Any]) -> Callable[..., Any]:
        setattr(method, EXCEPTION_HANDLER_ATTRIBUTE, ExceptionHandlerMapping(error_types, status))
        return method

    return record
