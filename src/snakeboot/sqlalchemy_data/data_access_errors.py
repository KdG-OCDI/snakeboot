from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from snakeboot.data import DataIntegrityViolationError, OptimisticLockingFailureError


@contextmanager
def translated_errors() -> Iterator[None]:
    """Raises SQLAlchemy's errors of data access in snakeboot's terms, like Spring's `PersistenceExceptionTranslator`.

    A row whose version changed meanwhile is an `OptimisticLockingFailureError`, a broken constraint a
    `DataIntegrityViolationError`, so an application answers them without knowing SQLAlchemy.
    """
    try:
        yield
    except StaleDataError as error:
        raise OptimisticLockingFailureError(f"The row changed since it was read: {error}") from error
    except IntegrityError as error:
        raise DataIntegrityViolationError(f"The database refused the change: {error.orig}") from error
