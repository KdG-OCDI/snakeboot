import importlib
import threading
from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Final, get_origin, override
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Dialect,
    Float,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    TypeDecorator,
    Uuid,
)
from sqlalchemy import Column as SqlColumn
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import Index as SqlIndex
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import registry
from sqlalchemy.types import TypeEngine

from snakeboot.data import Column, EntityDescription, Id, InvalidEntityError, Json, Property, Vector, description_of

_METADATA: Final = MetaData()
"""Every table of the process: an entity class is mapped once, whichever application context maps it first."""

_REGISTRY: Final = registry(metadata=_METADATA)
_MAPPING_LOCK: Final = threading.Lock()
_MAPPED: Final[dict[type, Table]] = {}


class AwareDateTime(TypeDecorator[datetime]):
    """A `timestamp with time zone` that is read back with its time zone in every database, SQLite's included.

    The domain refuses a naive `datetime`: a value is stored in UTC, and one read without a zone is UTC.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    @override
    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return value.astimezone(UTC) if value is not None and value.tzinfo is not None else value

    @override
    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


class EntityMapping:
    """The tables of an application's entities, each entity class mapped to its table, like JPA's metamodel.

    SQLAlchemy maps a plain dataclass to a table without the class knowing it ("imperative mapping"): the entities
    stay `snakeboot.data`'s, and only this binding names their columns' SQL types.
    """

    def __init__(self, tables: dict[type, Table]) -> None:
        self._tables = tables

    @classmethod
    def of(cls, entity_types: Iterable[type]) -> "EntityMapping":
        """Maps every entity class in `entity_types` to its table; a class mapped before keeps its table."""
        with _MAPPING_LOCK:
            return cls({entity_type: _mapped(description_of(entity_type)) for entity_type in entity_types})

    @property
    def entity_types(self) -> list[type]:
        """The entity classes, in the order of their qualified names."""
        return sorted(self._tables, key=lambda entity_type: f"{entity_type.__module__}.{entity_type.__qualname__}")

    @property
    def tables(self) -> list[Table]:
        """The tables of the entities, in the order of their names."""
        return sorted(self._tables.values(), key=lambda table: table.name)

    @property
    def metadata(self) -> MetaData:
        """The metadata that holds the tables (of the whole process: compare with `tables` alone)."""
        return _METADATA

    def table(self, entity_type: type) -> Table:
        """Returns the table of `entity_type`; an entity outside the component scan stops the call."""
        table = self._tables.get(entity_type)
        if table is None:
            raise InvalidEntityError(
                f"{entity_type.__qualname__} is not an entity of this application: its module is outside the "
                "component scan."
            )
        return table


def _mapped(description: EntityDescription) -> Table:
    table = _MAPPED.get(description.entity_type)
    if table is None:
        if description.table in _METADATA.tables:
            raise InvalidEntityError(f"Two entities name the table {description.table!r}.")
        table = _table_of(description)
        _REGISTRY.map_imperatively(description.entity_type, table)
        _MAPPED[description.entity_type] = table
    return table


def _table_of(description: EntityDescription) -> Table:
    table = Table(description.table, _METADATA, *(_column_of(description, prop) for prop in description.properties))
    for index in description.indexes:
        SqlIndex(index.name, *(table.c[column] for column in index.columns))
    return table


def _column_of(description: EntityDescription, prop: Property) -> SqlColumn[Any]:
    identifier, column = prop.marker(Id), prop.marker(Column) or Column()
    return SqlColumn(
        prop.name,
        _type_of(description, prop),
        primary_key=identifier is not None,
        autoincrement=identifier is not None and identifier.generated,
        nullable=prop.nullable and identifier is None,  # a number the database gives is never empty in a row
        unique=column.unique or None,
        index=column.index or None,
    )


def _type_of(description: EntityDescription, prop: Property) -> TypeEngine[Any]:  # noqa: PLR0911  # reason: one per type
    python_type, column, identifier = prop.python_type, prop.marker(Column), prop.marker(Id)
    if (vector := prop.marker(Vector)) is not None:
        return _vector(vector.dimensions)
    container = get_origin(python_type) or python_type
    if prop.marker(Json) is not None or container in {list, dict, tuple, Any, object}:
        return _json_of(container, nullable=prop.nullable)
    if python_type is str:
        return String(column.length) if column is not None and column.length else Text()
    if python_type is int:
        return BigInteger().with_variant(Integer(), "sqlite") if identifier and identifier.generated else Integer()
    simple: dict[Any, TypeEngine[Any]] = {
        bool: Boolean(),
        float: Float(),
        Decimal: Numeric(),
        UUID: Uuid(),
        datetime: AwareDateTime(),
        date: Date(),
        bytes: LargeBinary(),
    }
    if python_type in simple:
        return simple[python_type]
    if isinstance(python_type, type) and issubclass(python_type, Enum):
        return SqlEnum(python_type, native_enum=False, values_callable=lambda members: [m.value for m in members])
    raise InvalidEntityError(f"{description.entity_type.__name__}.{prop.name}: no column type for {python_type!r}.")


def _json_of(container: Any, *, nullable: bool) -> TypeEngine[Any]:
    # An empty field of a nullable column is SQL's NULL, not JSON's null, as with Django's JSONField(null=True).
    json: TypeEngine[Any] = JSON(none_as_null=nullable).with_variant(JSONB(none_as_null=nullable), "postgresql")
    # A change inside a list or a dict counts, as with Hibernate: `record.board[4] = "X"` then save() writes it.
    if container is list:
        return MutableList.as_mutable(json)
    return MutableDict.as_mutable(json) if container is dict else json


def _vector(dimensions: int) -> TypeEngine[Any]:
    try:
        pgvector = importlib.import_module("pgvector.sqlalchemy")
    except ModuleNotFoundError as error:
        raise InvalidEntityError("A Vector field needs pgvector: install snakeboot[vector].") from error
    vector_type: TypeEngine[Any] = pgvector.VECTOR(dimensions)
    return vector_type
