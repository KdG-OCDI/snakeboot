"""Technical library: entities and repositories in no persistence framework's terms, like Spring Data.

    @entity("tictactoe_game")                              # @Entity @Table(name = "tictactoe_game")
    @dataclass
    class GameRecord:
        game_id: Annotated[UUID, Id()]
        status: Annotated[str, Column(length=16)]
        board: list[str]

    class GameRecords(CrudRepository[GameRecord, UUID], Protocol):    # interface ... extends CrudRepository
        def find_by_status(self, status: str) -> list[GameRecord]: ...

An adapter asks for `GameRecords` by type and maps its records to the domain. snakeboot implements the interface
when its module is imported, and stops the start when it cannot. A `Version()` field guards against lost updates
(`OptimisticLockingFailureError`); `CreatedBy()` and `LastModifiedBy()` record who saved, from the `SecurityContext`.

It knows wireup and `snakeboot.security`: the binding of a persistence framework (`snakeboot.sqlalchemy_data`, when
the configuration has `[database]`) runs the queries, and its schema comes from SQL migrations, so an application
keeps its entities when the framework changes.
"""

from snakeboot.data.crud_repository import REPOSITORY_ATTRIBUTE, CrudRepository
from snakeboot.data.data_errors import (
    DataIntegrityViolationError,
    EmptyResultError,
    IncorrectResultSizeError,
    InvalidEntityError,
    InvalidRepositoryError,
    OptimisticLockingFailureError,
)
from snakeboot.data.derived_query import Action, Condition, DerivedQuery, Operator, Ordering, derive_query
from snakeboot.data.entity import (
    ENTITY_ATTRIBUTE,
    BigInt,
    Column,
    CreatedBy,
    CreatedDate,
    EntityDescription,
    ForeignKey,
    Id,
    Index,
    Json,
    LastModifiedBy,
    LastModifiedDate,
    OnDelete,
    Property,
    SmallInt,
    UniqueConstraint,
    Vector,
    Version,
    description_of,
    entity,
)
from snakeboot.data.query_methods import lock, query
from snakeboot.data.repository_operations import LockMode, NativeQuery, PageRequest, QueryCall, RepositoryOperations

__all__ = [
    "ENTITY_ATTRIBUTE",
    "REPOSITORY_ATTRIBUTE",
    "Action",
    "BigInt",
    "Column",
    "Condition",
    "CreatedBy",
    "CreatedDate",
    "CrudRepository",
    "DataIntegrityViolationError",
    "DerivedQuery",
    "EmptyResultError",
    "EntityDescription",
    "ForeignKey",
    "Id",
    "IncorrectResultSizeError",
    "Index",
    "InvalidEntityError",
    "InvalidRepositoryError",
    "Json",
    "LastModifiedBy",
    "LastModifiedDate",
    "LockMode",
    "NativeQuery",
    "OnDelete",
    "Operator",
    "OptimisticLockingFailureError",
    "Ordering",
    "PageRequest",
    "Property",
    "QueryCall",
    "RepositoryOperations",
    "SmallInt",
    "UniqueConstraint",
    "Vector",
    "Version",
    "derive_query",
    "description_of",
    "entity",
    "lock",
    "query",
]
