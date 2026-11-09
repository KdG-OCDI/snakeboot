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


class OptimisticLockingFailureError(RuntimeError):
    """Raised when a save or a delete finds that another transaction changed the entity's row since it was read.

    The entity has a `Version()` field, and the row no longer holds the number the entity was read with, like Spring's
    `OptimisticLockingFailureException`. Read the entity again and retry, or answer the caller with 409 Conflict.
    """


class DataIntegrityViolationError(RuntimeError):
    """Raised when the database refuses a change that breaks one of its constraints: a duplicate unique value, a
    missing foreign row, an empty column that may not be empty. Like Spring's `DataIntegrityViolationException`."""
