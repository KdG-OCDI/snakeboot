import re
from typing import Final

_WORD_BOUNDARY: Final = re.compile(r"(?<!^)(?=[A-Z])")


def error_answer(error: Exception) -> dict[str, str]:
    """Builds the error body `{"code": ..., "detail": ...}`, the shape of Spring's `ProblemDetail` in small.

    `code` is derived from the class name (`AlreadyRegisteredError` -> `already_registered`),
    so a client can rely on it; `detail` is the message, meant for developers.
    """
    name = type(error).__name__.removesuffix("Error")
    return {"code": _WORD_BOUNDARY.sub("_", name).lower(), "detail": str(error)}
