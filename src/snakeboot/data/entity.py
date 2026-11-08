import dataclasses
import functools
import operator
import types
import typing
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, Union, get_args, get_origin

from snakeboot.data.data_errors import InvalidEntityError

ENTITY_ATTRIBUTE: Final = "__snakeboot_entity__"
"""Set on every class marked with `@entity`, so the component scan finds the entities of the application."""


@dataclass(frozen=True, slots=True)
class Id:
    """Marks the identifier of an entity, like JPA's `@Id`; `generated=True` lets the database number it."""

    generated: bool = False


@dataclass(frozen=True, slots=True)
class Column:
    """Details a column, like JPA's `@Column`: a `length` for text, `unique`, and an `index` of its own."""

    length: int | None = None
    unique: bool = False
    index: bool = False


@dataclass(frozen=True, slots=True)
class CreatedDate:
    """Marks a `datetime | None` that `save` fills when the entity is first saved, like Spring Data's `@CreatedDate`."""


@dataclass(frozen=True, slots=True)
class LastModifiedDate:
    """Marks a `datetime | None` that every `save` fills, like Spring Data's `@LastModifiedDate`."""


@dataclass(frozen=True, slots=True)
class Json:
    """Marks a field stored as JSON whatever its type, like JPA's `@JdbcTypeCode(SqlTypes.JSON)`.

    A field of type `Any` is JSON without it: any value JSON can hold (a number, a text, a list, an object) is stored
    and read back as it was. `list` and `dict` fields are JSON anyway.
    """


@dataclass(frozen=True, slots=True)
class Vector:
    """Marks a `list[float]` stored as a vector of `dimensions` numbers, for similarity search (pgvector)."""

    dimensions: int


@dataclass(frozen=True, slots=True)
class Index:
    """An index over one or more columns of an entity's table, like JPA's `@Index`."""

    name: str
    columns: tuple[str, ...]

    def __init__(self, name: str, *columns: str) -> None:
        if not columns:
            raise InvalidEntityError(f"The index {name!r} names no column.")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "columns", columns)


type Marker = Id | Column | CreatedDate | LastModifiedDate | Json | Vector

_MARKERS: Final = (Id, Column, CreatedDate, LastModifiedDate, Json, Vector)


@dataclass(frozen=True, slots=True)
class Property:
    """One field of an entity: its name, its Python type without `None`, whether it may be empty, its markers."""

    name: str
    python_type: Any
    nullable: bool
    markers: tuple[Marker, ...]

    def marker[M](self, marker_type: type[M]) -> M | None:
        """Returns the marker of `marker_type` on this property, or None."""
        return next((marker for marker in self.markers if isinstance(marker, marker_type)), None)


@dataclass(frozen=True, slots=True)
class EntityDescription:
    """What `@entity` declared: the class, its table, its properties in field order, its identifier, its indexes."""

    entity_type: type
    table: str
    properties: tuple[Property, ...]
    indexes: tuple[Index, ...]

    @property
    def identifier(self) -> Property:
        """The property marked with `Id`."""
        return next(prop for prop in self.properties if prop.marker(Id) is not None)

    def property_named(self, name: str) -> Property | None:
        """Returns the property `name`, or None."""
        return next((prop for prop in self.properties if prop.name == name), None)


def entity[C: type](table: str, *, indexes: tuple[Index, ...] = ()) -> Callable[[C], C]:
    """Declares a dataclass whose objects a table keeps, like JPA's `@Entity` with `@Table(name=table)`.

        @entity("tictactoe_game", indexes=(Index("tictactoe_game_waiting_idx", "status", "join_deadline"),))
        @dataclass
        class GameRecord:
            game_id: Annotated[UUID, Id()]
            player_x_id: Annotated[str, Column(length=100)]
            board: list[str]                                   # JSON
            join_deadline: datetime | None                      # an empty column
            updated_at: Annotated[datetime | None, LastModifiedDate()] = None

    A field's type is its column's: `str`, `int`, `float`, `bool`, `Decimal`, `UUID`, `datetime` (with its time zone),
    `date`, and `list`, `dict` or `Any` as JSON (`Json()` makes any field JSON); `X | None` may be empty. The class knows no persistence framework, so a
    domain or an adapter keeps it free of one. It is a plain, mutable dataclass: the persistence framework sets its
    fields. Everything is checked here, when the module is imported.
    """

    def declare(entity_type: C) -> C:
        description = _describe(entity_type, table, indexes)
        setattr(entity_type, ENTITY_ATTRIBUTE, description)
        return entity_type

    return declare


def description_of(entity_type: type) -> EntityDescription:
    """Returns what `@entity` declared on `entity_type`; a class that is no entity stops the start."""
    description = vars(entity_type).get(ENTITY_ATTRIBUTE)
    if not isinstance(description, EntityDescription):
        raise InvalidEntityError(f"{entity_type.__qualname__} is not an @entity.")
    return description


def _describe(entity_type: type, table: str, indexes: tuple[Index, ...]) -> EntityDescription:
    if not dataclasses.is_dataclass(entity_type):
        raise InvalidEntityError(f"@entity marks a dataclass: put @dataclass under @entity on {entity_type.__name__}.")
    parameters = vars(entity_type)["__dataclass_params__"]
    if parameters.frozen or "__slots__" in vars(entity_type):
        raise InvalidEntityError(
            f"{entity_type.__name__} is frozen or has slots: the persistence framework sets the fields of an entity."
        )
    hints = typing.get_type_hints(entity_type, include_extras=True)
    properties = tuple(_property(field.name, hints[field.name]) for field in dataclasses.fields(entity_type))
    description = EntityDescription(entity_type, table, properties, indexes)
    _refuse_wrong_identifiers(description)
    _refuse_unknown_index_columns(description)
    return description


def _property(name: str, annotation: Any) -> Property:
    markers: tuple[Marker, ...] = ()
    if get_origin(annotation) is typing.Annotated:
        annotation, *extras = get_args(annotation)
        markers = tuple(extra for extra in extras if isinstance(extra, _MARKERS))
    python_type, nullable = _without_none(annotation)
    return Property(name, python_type, nullable, markers)


def _without_none(annotation: Any) -> tuple[Any, bool]:
    # `int | None` is an int that may be empty; `int | str | None` is `int | str` that may be empty.
    if get_origin(annotation) not in {Union, types.UnionType}:
        return annotation, False
    arguments = get_args(annotation)
    others = [argument for argument in arguments if argument is not type(None)]
    nullable = len(others) < len(arguments)
    if len(others) == 1 or not nullable:
        return (others[0] if len(others) == 1 else annotation), nullable
    return functools.reduce(operator.or_, others), nullable


def _refuse_wrong_identifiers(description: EntityDescription) -> None:
    identifiers = [prop.name for prop in description.properties if prop.marker(Id) is not None]
    if len(identifiers) != 1:
        raise InvalidEntityError(
            f"{description.entity_type.__name__} marks {len(identifiers)} fields with Id(): an entity has one "
            "identifier, `Annotated[UUID, Id()]` say."
        )


def _refuse_unknown_index_columns(description: EntityDescription) -> None:
    for index in description.indexes:
        unknown = [column for column in index.columns if description.property_named(column) is None]
        if unknown:
            raise InvalidEntityError(
                f"The index {index.name!r} of {description.entity_type.__name__} names unknown fields: {unknown}."
            )
