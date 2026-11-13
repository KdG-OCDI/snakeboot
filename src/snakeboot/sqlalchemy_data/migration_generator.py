import io
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Final

from alembic.autogenerate import produce_migrations
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.operations.ops import AlterColumnOp, MigrateOperation, ModifyTableOps
from sqlalchemy import MetaData

from snakeboot.sqlalchemy_data.database import Database
from snakeboot.sqlalchemy_data.entity_mapping import EntityMapping
from snakeboot.sqlalchemy_data.schema_migrations import (
    HISTORY_TABLE,
    MIGRATION_FILE,
    InvalidMigrationError,
    SchemaMigrations,
    migration_locations,
)

_DESCRIPTION: Final = re.compile(r"[^a-z0-9]+")

_CONSTRAINTS: Final = frozenset({"unique_constraint", "foreign_key_constraint"})

type _ObjectFilter = Callable[[Any, str | None, str, bool, Any], bool]
"""Alembic's include_object hook: whether autogenerate compares an object, given its kind and where it was found."""


class MigrationGenerator:
    """Writes the SQL that brings the database's schema to the entities, as the next migration.

    Alembic compares the tables of the entities with the database, which must have run every migration, and the
    difference is written as plain SQL in the database's dialect: the migration stays readable, and stays valid when
    the persistence framework changes. A table the entities do not know is never dropped.
    """

    def __init__(self, database: Database, mapping: EntityMapping, migrations: SchemaMigrations) -> None:
        self._database = database
        self._mapping = mapping
        self._migrations = migrations

    def changes(self) -> str:
        """Returns the SQL statements the schema lacks, or an empty text when it fits the entities.

        Alembic compares a foreign key by its columns, its target, `ON DELETE` and whether it is deferred, not by its
        name, and a partial index without its condition: a schema that differs only there fits.
        """
        return _sql_of(self._operations(_known, compare_types=True), self._database.engine.dialect.name)

    def changes_sqlite_shows(self) -> str:
        """Returns, in PostgreSQL's SQL, the tables, columns, NOT NULLs and indexes the schema lacks, or an empty text.

        For a schema on SQLite that migrations written for PostgreSQL built, as in the database in memory of a test.
        SQLite keeps whatever type name a migration declares, records no NOT NULL that a primary key implies, and shows
        not every unique constraint or foreign key: the types and the constraints are left to `changes()` on PostgreSQL.
        """
        keys = {(table.name, column.name) for table in self._mapping.tables for column in table.primary_key}
        operations = self._operations(_known_without_constraints, compare_types=False)
        return _sql_of([operation for operation in operations if not _key_made_not_null(operation, keys)], "postgresql")

    def write(self, description: str, sql: str, into: Path | None = None) -> Path:
        """Writes `sql` as the migration after the last one, in `into` or the one migrations directory there is."""
        location = into or self._only_location()
        location.mkdir(parents=True, exist_ok=True)
        version = max((migration.version[0] for migration in self._migrations.migrations), default=0) + 1
        path = location / f"V{version}__{_DESCRIPTION.sub('_', description.lower()).strip('_')}.sql"
        if MIGRATION_FILE.fullmatch(path.name) is None:
            raise InvalidMigrationError(f"{description!r} gives no migration name: describe it in words.")
        path.write_text(sql, encoding="utf-8", newline="\n")
        return path

    def _operations(self, include: _ObjectFilter, *, compare_types: bool) -> list[MigrateOperation]:
        if pending := self._migrations.pending():
            names = ", ".join(migration.path.name for migration in pending)
            raise InvalidMigrationError(f"The database has not run {names}: run migrate before make_migration.")
        target = MetaData()
        for table in self._mapping.tables:
            table.to_metadata(target)
        with self._database.engine.connect() as connection:
            comparing = MigrationContext.configure(
                connection, opts={"compare_type": compare_types, "include_object": include, "target_metadata": target}
            )
            operations = produce_migrations(comparing, target).upgrade_ops
            return list(_flattened(operations.ops if operations else []))

    def _only_location(self) -> Path:
        locations = migration_locations(self._mapping.entity_types)
        if len(locations) != 1:
            raise InvalidMigrationError(
                f"The entities live in {len(locations)} packages: say which one's migrations directory to write in "
                "with --into."
            )
        return locations[0]


def _known(  # noqa: PLR0917  # reason: Alembic calls its include_object hook with five positional arguments
    _object: Any,
    name: str | None,
    type_: str,
    reflected: bool,  # noqa: FBT001  # reason: as Alembic passes it
    compare_to: Any,
) -> bool:
    # The history table, and any table the entities do not declare, stay as they are.
    return not (type_ == "table" and (name == HISTORY_TABLE or (reflected and compare_to is None)))


def _known_without_constraints(  # noqa: PLR0917  # reason: Alembic calls its include_object hook with five positional arguments
    object_: Any,
    name: str | None,
    type_: str,
    reflected: bool,  # noqa: FBT001  # reason: as Alembic passes it
    compare_to: Any,
) -> bool:
    # SQLite's reflection misses a UNIQUE written next to a column's type, and has no name for a foreign key that the
    # migration left unnamed: the constraints are compared on PostgreSQL.
    return type_ not in _CONSTRAINTS and _known(object_, name, type_, reflected, compare_to)


def _key_made_not_null(operation: MigrateOperation, keys: set[tuple[str, str]]) -> bool:
    # PostgreSQL makes every column of a primary key NOT NULL; SQLite records only the NOT NULL a migration writes.
    return (
        isinstance(operation, AlterColumnOp)
        and operation.modify_nullable is False
        and (operation.table_name, operation.column_name) in keys
    )


def _flattened(operations: list[MigrateOperation]) -> Iterator[MigrateOperation]:
    for operation in operations:
        if isinstance(operation, ModifyTableOps):
            yield from _flattened(operation.ops)
        else:
            yield operation


def _sql_of(operations: list[MigrateOperation], dialect_name: str) -> str:
    buffer = io.StringIO()
    rendering = MigrationContext.configure(
        dialect_name=dialect_name, opts={"as_sql": True, "output_buffer": buffer, "literal_binds": True}
    )
    writer = Operations(rendering)
    for operation in operations:
        writer.invoke(operation)
    # Alembic ends some lines with a space; a hook that trims it would change the checksum of a migration that ran.
    lines = (line.rstrip() for line in buffer.getvalue().strip().splitlines())
    return "\n".join(lines) + "\n" if operations else ""
