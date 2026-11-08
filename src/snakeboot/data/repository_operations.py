from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from snakeboot.data.derived_query import DerivedQuery
from snakeboot.data.entity import EntityDescription


class LockMode(StrEnum):
    """How a query locks the rows it reads until the transaction ends, like JPA's `LockModeType`."""

    PESSIMISTIC_WRITE = "pessimistic_write"
    """`SELECT ... FOR UPDATE`: no other transaction changes or locks the rows meanwhile."""
    PESSIMISTIC_READ = "pessimistic_read"
    """`SELECT ... FOR SHARE`: other transactions may read and share-lock the rows, not change them."""


@dataclass(frozen=True, slots=True)
class PageRequest:
    """Which slice of the rows a query returns, like Spring Data's `Pageable`: skip `offset`, return `limit`."""

    offset: int
    limit: int

    @classmethod
    def of(cls, page: int, size: int) -> "PageRequest":
        """Returns page `page` (from 0) of `size` rows, as Spring's `PageRequest.of(page, size)`."""
        return cls(offset=page * size, limit=size)


@dataclass(frozen=True, slots=True)
class QueryCall:
    """One call of a derived query: the entity, the query, its arguments in the order of the name, a page, a lock."""

    entity: EntityDescription
    query: DerivedQuery
    arguments: tuple[Any, ...]
    page: PageRequest | None = None
    lock: LockMode | None = None


@dataclass(frozen=True, slots=True)
class NativeQuery:
    """A query written in SQL (`@query`): its text, whether it changes rows, and the type of one result.

    A result of an entity type is that entity; of a scalar type (`int`, `str`, ...) the first column; of any other
    type the object made from the row's columns by name, a dataclass or a Pydantic model say.
    """

    sql: str
    modifying: bool
    result_type: Any


class RepositoryOperations(ABC):
    """What the repositories of `snakeboot.data` ask of a persistence framework, which implements it.

    The persistence framework's binding registers its implementation as a component; every repository receives it.
    """

    @abstractmethod
    def save(self, entity: Any) -> Any:
        """Inserts `entity`, or updates the row with its identifier, and returns the saved entity."""

    @abstractmethod
    def delete(self, entity: Any) -> None:
        """Deletes the row of `entity`."""

    @abstractmethod
    def find(self, call: QueryCall) -> list[Any]:
        """Returns the entities the call selects, in the call's order and page."""

    @abstractmethod
    def count(self, call: QueryCall) -> int:
        """Returns how many rows the call selects."""

    @abstractmethod
    def exists(self, call: QueryCall) -> bool:
        """Tells whether the call selects a row."""

    @abstractmethod
    def delete_where(self, call: QueryCall) -> int:
        """Deletes the rows the call selects and returns how many."""

    @abstractmethod
    def select(self, query: NativeQuery, arguments: Mapping[str, Any]) -> list[Any]:
        """Runs a SQL query with named `arguments` and returns its results."""

    @abstractmethod
    def update(self, query: NativeQuery, arguments: Mapping[str, Any]) -> int:
        """Runs a SQL statement that changes rows and returns how many it changed."""
