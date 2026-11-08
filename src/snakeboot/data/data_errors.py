class InvalidEntityError(TypeError):
    """Raised when a class cannot be an entity: the start stops instead of failing at the first query."""


class InvalidRepositoryError(TypeError):
    """Raised when a repository declares a method snakeboot cannot implement: a name it cannot read, a field the
    entity does not have, a parameter too many or too few. The start stops instead of failing at the first call."""


class IncorrectResultSizeError(LookupError):
    """Raised when a method that returns one entity finds several.

    Like Spring's `IncorrectResultSizeDataAccessException`.
    """


class EmptyResultError(LookupError):
    """Raised when a method that returns exactly one entity (`-> GameRecord`, not `-> GameRecord | None`) finds none,
    like Spring's `EmptyResultDataAccessException`."""
