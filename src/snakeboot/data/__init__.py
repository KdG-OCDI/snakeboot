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
when its module is imported, and stops the start when it cannot. It knows wireup and nothing else: the binding of a
persistence framework (`snakeboot.sqlalchemy_data`, when the configuration has `[database]`) runs the queries, and
its schema comes from SQL migrations, so an application keeps its entities when the framework changes.
"""

from snakeboot.data.crud_repository import REPOSITORY_ATTRIBUTE, CrudRepository
from snakeboot.data.data_errors import (
    EmptyResultError,
    IncorrectResultSizeError,
    InvalidEntityError,
    InvalidRepositoryError,
)
from snakeboot.data.derived_query import Action, Condition, DerivedQuery, Operator, Ordering, derive_query
from snakeboot.data.entity import (
    ENTITY_ATTRIBUTE,
    Column,
    CreatedDate,
    EntityDescription,
    Id,
    Index,
    Json,
    LastModifiedDate,
    Property,
    Vector,
    description_of,
    entity,
)
from snakeboot.data.query_methods import lock, query
from snakeboot.data.repository_operations import LockMode, NativeQuery, PageRequest, QueryCall, RepositoryOperations

__all__ = [
    "ENTITY_ATTRIBUTE",
    "REPOSITORY_ATTRIBUTE",
    "Action",
    "Column",
    "Condition",
    "CreatedDate",
    "CrudRepository",
    "DerivedQuery",
    "EmptyResultError",
    "EntityDescription",
    "Id",
    "IncorrectResultSizeError",
    "Index",
    "InvalidEntityError",
    "InvalidRepositoryError",
    "Json",
    "LastModifiedDate",
    "LockMode",
    "NativeQuery",
    "Operator",
    "Ordering",
    "PageRequest",
    "Property",
    "QueryCall",
    "RepositoryOperations",
    "Vector",
    "derive_query",
    "description_of",
    "entity",
    "lock",
    "query",
]
