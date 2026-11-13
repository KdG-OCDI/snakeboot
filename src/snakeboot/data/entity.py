import dataclasses
import functools
import operator
import types
import typing
from collections.abc import Callable
from dataclasses import KW_ONLY, dataclass
from typing import Any, Final, Literal, Union, get_args, get_origin

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
class CreatedBy:
    """Marks a `str | None` that `save` fills, when the entity is first saved, with the name of the signed-in
    principal, like Spring Data's `@CreatedBy`; without one it stays empty."""


@dataclass(frozen=True, slots=True)
class LastModifiedBy:
    """Marks a `str | None` that every `save` fills with the name of the signed-in principal, or empties without
    one, like Spring Data's `@LastModifiedBy`."""


@dataclass(frozen=True, slots=True)
class Version:
    """Marks the `int` that guards an entity against lost updates, like JPA's `@Version`.

    Every update raises it by one, on the condition that the row still holds the number the entity was read with; when
    another transaction changed the row meanwhile, the save raises `OptimisticLockingFailureError` (answer it with 409).
    A new entity gets 1. Declare it `Annotated[int | None, Version()] = None`, a column that may be empty; for a
    `NOT NULL` column, as in a schema another tool made, `Annotated[int, Version()] = 0`.
    """


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
class BigInt:
    """Marks an `int` kept in 64 bits, like Java's `long`: BIGINT, for numbers past 2,147,483,647 (amounts, say).

    SQLite keeps every whole number alike, so it matters on PostgreSQL. A generated identifier is a BIGINT anyway.
    """


@dataclass(frozen=True, slots=True)
class SmallInt:
    """Marks an `int` kept in 16 bits, like Java's `short`: SMALLINT, from -32,768 to 32,767.

    SQLite keeps every whole number alike, so it matters on PostgreSQL.
    """


type OnDelete = Literal["cascade", "set null", "set default", "restrict", "no action"]
"""What the database does to the rows that refer to a row being deleted, as SQL's `ON DELETE` says it."""

_ON_DELETE: Final = frozenset({"cascade", "set null", "set default", "restrict", "no action"})


@dataclass(frozen=True, slots=True)
class ForeignKey:
    """Marks a column that refers to the key of another entity's table, like JPA's `@JoinColumn` with `@ForeignKey`.

        funding_call_id: Annotated[int, ForeignKey("funding_call.id", on_delete="cascade")]

    `target` is `table.column`, a column of an entity of the same application. `on_delete` is what the database does
    to the rows that refer to a deleted row, like Hibernate's `@OnDelete`: "cascade" deletes them, "set null" empties
    the column; without it the delete fails with a `DataIntegrityViolationError` while such rows exist. `name` is the
    constraint's, for a schema that has its own names; without it the database chooses one. `deferred=True` checks
    the key at the commit instead of at each statement (`DEFERRABLE INITIALLY DEFERRED`), as Django declares every
    foreign key on PostgreSQL. There is no relationship: loading the rows that refer to one is a repository's job, as
    in Spring Data JDBC.
    """

    target: str
    _: KW_ONLY
    on_delete: OnDelete | None = None
    name: str | None = None
    deferred: bool = False

    def __post_init__(self) -> None:
        table, _, column = self.target.partition(".")
        if not table or not column or "." in column:
            raise InvalidEntityError(f"The foreign key {self.target!r} names no column: write `table.column`.")
        if self.on_delete is not None and self.on_delete not in _ON_DELETE:
            raise InvalidEntityError(
                f"The foreign key to {self.target} has on_delete={self.on_delete!r}; it is one of {sorted(_ON_DELETE)}."
            )


@dataclass(frozen=True, slots=True)
class Index:
    """An index over one or more columns of an entity's table, like JPA's `@Index`.

        Index("funding_template_source_url_uniq", "source_url", unique=True, where="origin = 'found_at_source'")

    `unique=True` refuses a second row with the same values in those columns, like JPA's `@Index(unique = true)`: the
    insert or update fails with a `DataIntegrityViolationError`. `where`, an SQL condition, makes the index partial:
    it holds only the rows that meet it, as on PostgreSQL and SQLite. On PostgreSQL a unique index and a
    `UniqueConstraint` are different objects: declare the one the schema has.
    """

    name: str
    columns: tuple[str, ...]
    unique: bool
    where: str | None

    def __init__(self, name: str, *columns: str, unique: bool = False, where: str | None = None) -> None:
        if not columns:
            raise InvalidEntityError(f"The index {name!r} names no column.")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "columns", columns)
        object.__setattr__(self, "unique", unique)
        object.__setattr__(self, "where", where)


@dataclass(frozen=True, slots=True)
class UniqueConstraint:
    """A unique constraint over one or more columns of an entity's table, like JPA's `@UniqueConstraint`.

        UniqueConstraint("funding_deadline_call_stage_uniq", "funding_call_id", "stage")

    A second row with the same values in those columns fails with a `DataIntegrityViolationError`. For a condition,
    a unique `Index` with `where` is the partial one.
    """

    name: str
    columns: tuple[str, ...]

    def __init__(self, name: str, *columns: str) -> None:
        if not columns:
            raise InvalidEntityError(f"The unique constraint {name!r} names no column.")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "columns", columns)


type Marker = (
    Id
    | Column
    | CreatedDate
    | LastModifiedDate
    | CreatedBy
    | LastModifiedBy
    | Version
    | Json
    | Vector
    | BigInt
    | SmallInt
    | ForeignKey
)

_MARKERS: Final = (
    Id,
    Column,
    CreatedDate,
    LastModifiedDate,
    CreatedBy,
    LastModifiedBy,
    Version,
    Json,
    Vector,
    BigInt,
    SmallInt,
    ForeignKey,
)


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
    """What `@entity` declared: the class, its table, its properties in field order, its identifier, its indexes and
    its unique constraints."""

    entity_type: type
    table: str
    properties: tuple[Property, ...]
    indexes: tuple[Index, ...]
    unique_constraints: tuple[UniqueConstraint, ...]

    @property
    def identifier(self) -> Property:
        """The property marked with `Id`."""
        return next(prop for prop in self.properties if prop.marker(Id) is not None)

    @property
    def version(self) -> Property | None:
        """The property marked with `Version`, or None for an entity without optimistic locking."""
        return next((prop for prop in self.properties if prop.marker(Version) is not None), None)

    def property_named(self, name: str) -> Property | None:
        """Returns the property `name`, or None."""
        return next((prop for prop in self.properties if prop.name == name), None)


def entity[C: type](
    table: str, *, indexes: tuple[Index, ...] = (), unique_constraints: tuple[UniqueConstraint, ...] = ()
) -> Callable[[C], C]:
    """Declares a dataclass whose objects a table keeps, like JPA's `@Entity` with `@Table(name = table, indexes = ...,
    uniqueConstraints = ...)`.

        @entity("tictactoe_game", indexes=(Index("tictactoe_game_waiting_idx", "status", "join_deadline"),))
        @dataclass
        class GameRecord:
            game_id: Annotated[UUID, Id()]
            player_x_id: Annotated[str, Column(length=100)]
            board: list[str]                                   # JSON
            join_deadline: datetime | None                      # an empty column
            updated_at: Annotated[datetime | None, LastModifiedDate()] = None
            updated_by: Annotated[str | None, LastModifiedBy()] = None   # who, from the SecurityContext
            version: Annotated[int | None, Version()] = None             # optimistic locking

    A field's type is its column's: `str`, `int`, `float`, `bool`, `Decimal`, `UUID`, `datetime` (with its time zone),
    `date`, and `list`, `dict` or `Any` as JSON (`Json()` makes any field JSON); `X | None` may be empty. An `int` is
    an INTEGER, or a BIGINT with `BigInt()` and a SMALLINT with `SmallInt()`; `ForeignKey(...)` makes a column refer
    to another entity's table. The class knows no persistence framework, so a domain or an adapter keeps it free of
    one. It is a plain, mutable dataclass: the persistence framework sets its fields. Everything is checked here, when
    the module is imported; that a foreign key refers to an entity's table, when the application starts.
    """

    def declare(entity_type: C) -> C:
        description = _describe(entity_type, table, indexes=indexes, unique_constraints=unique_constraints)
        setattr(entity_type, ENTITY_ATTRIBUTE, description)
        return entity_type

    return declare


def description_of(entity_type: type) -> EntityDescription:
    """Returns what `@entity` declared on `entity_type`; a class that is no entity stops the start."""
    description = vars(entity_type).get(ENTITY_ATTRIBUTE)
    if not isinstance(description, EntityDescription):
        raise InvalidEntityError(f"{entity_type.__qualname__} is not an @entity.")
    return description


def _describe(
    entity_type: type, table: str, *, indexes: tuple[Index, ...], unique_constraints: tuple[UniqueConstraint, ...]
) -> EntityDescription:
    if not dataclasses.is_dataclass(entity_type):
        raise InvalidEntityError(f"@entity marks a dataclass: put @dataclass under @entity on {entity_type.__name__}.")
    parameters = vars(entity_type)["__dataclass_params__"]
    if parameters.frozen or "__slots__" in vars(entity_type):
        raise InvalidEntityError(
            f"{entity_type.__name__} is frozen or has slots: the persistence framework sets the fields of an entity."
        )
    hints = typing.get_type_hints(entity_type, include_extras=True)
    properties = tuple(_property(field.name, hints[field.name]) for field in dataclasses.fields(entity_type))
    description = EntityDescription(entity_type, table, properties, indexes, unique_constraints)
    _refuse_wrong_identifiers(description)
    _refuse_wrong_versions(description)
    _refuse_wrong_auditors(description)
    _refuse_wrong_integer_sizes(description)
    _refuse_set_null_on_a_column_that_is_never_empty(description)
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


def _refuse_wrong_versions(description: EntityDescription) -> None:
    versions = [prop for prop in description.properties if prop.marker(Version) is not None]
    name = description.entity_type.__name__
    if len(versions) > 1:
        raise InvalidEntityError(f"{name} marks {len(versions)} fields with Version(): an entity has one version.")
    if versions and versions[0].python_type is not int:
        raise InvalidEntityError(f"{name}.{versions[0].name} is a Version(), so it is an `int | None`.")


def _refuse_wrong_auditors(description: EntityDescription) -> None:
    for prop in description.properties:
        auditor = prop.marker(CreatedBy) or prop.marker(LastModifiedBy)
        if auditor is not None and (prop.python_type is not str or not prop.nullable):
            raise InvalidEntityError(
                f"{description.entity_type.__name__}.{prop.name} is a {type(auditor).__name__}(), so it is a "
                "`str | None`: work that nobody signed in to leaves it empty."
            )


def _refuse_wrong_integer_sizes(description: EntityDescription) -> None:
    for prop in description.properties:
        sizes = [f"{type(marker).__name__}()" for marker in prop.markers if isinstance(marker, BigInt | SmallInt)]
        if sizes and (prop.python_type is not int or len(sizes) > 1):
            raise InvalidEntityError(
                f"{description.entity_type.__name__}.{prop.name} is a {' and a '.join(sizes)}, so it is an `int` of "
                "one size."
            )


def _refuse_set_null_on_a_column_that_is_never_empty(description: EntityDescription) -> None:
    for prop in description.properties:
        foreign_key = prop.marker(ForeignKey)
        if foreign_key is not None and foreign_key.on_delete == "set null" and not prop.nullable:
            raise InvalidEntityError(
                f'{description.entity_type.__name__}.{prop.name} refers to {foreign_key.target} with on_delete="set '
                'null", so it may be empty: `... | None`.'
            )


def _refuse_unknown_index_columns(description: EntityDescription) -> None:
    for kind, declared in (("index", description.indexes), ("unique constraint", description.unique_constraints)):
        for each in declared:
            unknown = [column for column in each.columns if description.property_named(column) is None]
            if unknown:
                raise InvalidEntityError(
                    f"The {kind} {each.name!r} of {description.entity_type.__name__} names unknown fields: {unknown}."
                )
