"""The database in memory of a test: SQLite, on the schema the application's own migrations build."""

import sqlite3
import threading
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any, Final, cast, override
from uuid import UUID

from sqlalchemy import Connection, Dialect, StaticPool, Uuid, create_engine
from sqlalchemy.dialects import registry
from sqlalchemy.dialects.sqlite.pysqlite import SQLiteDialect_pysqlite
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import ConnectionPoolEntry

from snakeboot.sqlalchemy_data.database import Database
from snakeboot.sqlalchemy_data.entity_mapping import EntityMapping
from snakeboot.sqlalchemy_data.migration_generator import MigrationGenerator
from snakeboot.sqlalchemy_data.schema_migrations import (
    InvalidMigrationError,
    Migration,
    SchemaMigrations,
    migration_locations,
    migrations_in,
)
from snakeboot.sqlalchemy_data.sqlite import open_transactions_with_sqlalchemy

if TYPE_CHECKING:
    from sqlalchemy.sql.type_api import _BindProcessorType

HOLD_SECONDS: Final = 10
"""How long a thread waits for the connection another holds, before the test fails instead of hanging."""

_POSTGRESQL_HINT: Final = (
    "A migration in PostgreSQL's own SQL is tested on PostgreSQL, in a container: "
    "@application_test(database=PostgreSQLContainer())."
)


class OneThreadAtATimePool(StaticPool):
    """SQLAlchemy's pool of one connection, lent to one thread at a time.

    Every thread of a test shares the one connection of an SQLite in memory, so a test's server threads see what the
    test wrote. Lent to two threads at once, the second would begin a transaction inside the first's. The lock is
    taken before the pool hands out its connection, and given back with it: a thread that waits touches nothing of
    the connection another holds. Reentrant, so a thread that holds it may take it once more.
    """

    def __init__(self, *arguments: Any, **options: Any) -> None:
        super().__init__(*arguments, **options)
        self._holder = threading.RLock()

    @override
    def _do_get(self) -> ConnectionPoolEntry:
        if not self._holder.acquire(timeout=HOLD_SECONDS):
            raise TimeoutError(
                f"Another thread held the database in memory for {HOLD_SECONDS} seconds: does a test wait, inside a "
                "transaction, for a call to the API or for a background thread?"
            )
        return super()._do_get()

    @override
    def _do_return_conn(self, record: ConnectionPoolEntry) -> None:
        super()._do_return_conn(record)
        self._holder.release()


class _UuidWithDashes(Uuid[UUID]):
    """A UUID that a test's SQLite keeps as text with its dashes, whatever type name its column was declared with.

    SQLAlchemy writes a UUID in SQLite as 32 hexadecimal digits. A migration written for PostgreSQL declares the column
    `UUID`, which SQLite reads as a number where it can: `UUID(int=7)` would be kept as 7, and two UUIDs of decimal
    digits only as one rounded number. With its dashes, a UUID is never a number.
    """

    cache_ok = True

    @override
    def bind_processor(self, dialect: Dialect) -> "_BindProcessorType[UUID] | None":
        def process(value: UUID | None) -> str | None:
            return None if value is None else str(value)

        return process


class _SQLiteOfATest(SQLiteDialect_pysqlite):
    """SQLite as a test runs it: Python's sqlite3, with a UUID kept as text with its dashes (`_UuidWithDashes`)."""

    supports_statement_cache = True
    colspecs = {**SQLiteDialect_pysqlite.colspecs, Uuid: _UuidWithDashes}  # noqa: RUF012  # reason: a dialect declares them so


registry.register("sqlite.snakeboot_test", __name__, _SQLiteOfATest.__name__)


def in_memory_database(entity_types: Iterable[type] = (), *, migrations: Sequence[Migration] | None = None) -> Database:
    """Returns a fresh SQLite database in memory, with savepoints and foreign keys, for tests.

    Every thread shares its one connection, so a test's server threads see what the test wrote, and one thread at a
    time holds it (`OneThreadAtATimePool`): the test, a call to the API, the scheduler, a listener or the event
    publication registry never begin a transaction inside another's. SQLAlchemy opens its transactions, with
    savepoints and foreign keys, as for a file of `[database]` (`open_transactions_with_sqlalchemy`).

    With `entity_types`, it holds their tables, as the application's own migrations build them: those next to the
    entities, or `migrations`, the same ones `migrate` runs. They run once per process, in a template database that
    every test then copies; first the migrated schema is compared with the entities, like Hibernate's
    `ddl-auto=validate`, and a migration SQLite rejects, or a table, column, NOT NULL or index the migrations lack,
    stops every test on them (`InvalidMigrationError`). Without migrations, the tables come from the entities.
    """
    mapping = EntityMapping.of(entity_types)
    if not mapping.entity_types and not migrations:
        return _empty_database()
    found = migrations_in(migration_locations(mapping.entity_types)) if migrations is None else migrations
    return _copy_of(_TEMPLATES.template_for(mapping, found))


def _empty_database() -> Database:
    engine = create_engine(
        "sqlite+snakeboot_test://", connect_args={"check_same_thread": False}, poolclass=OneThreadAtATimePool
    )
    open_transactions_with_sqlalchemy(engine, begin="BEGIN")
    return Database(engine)


def _copy_of(template: Database) -> Database:
    """A fresh database with what `template` holds, copied by SQLite's backup: quicker than creating the tables."""
    database = _empty_database()
    with template.engine.connect() as source, database.engine.connect() as target:
        _sqlite3_of(source).backup(_sqlite3_of(target))
    return database


class _Templates:
    """The template databases of the process, one per set of entities and migrations, each built the first time."""

    def __init__(self) -> None:
        self._built: dict[tuple[object, ...], Database | InvalidMigrationError] = {}
        self._lock = threading.Lock()

    def template_for(self, mapping: EntityMapping, migrations: Sequence[Migration]) -> Database:
        """Returns the template database `migrations` built for `mapping`, building it the first time."""
        key = (*mapping.entity_types, *(f"{migration.label}:{migration.checksum}" for migration in migrations))
        with self._lock:
            if key not in self._built:
                self._built[key] = _built_template(mapping, migrations)
            built = self._built[key]
        if isinstance(built, InvalidMigrationError):
            raise InvalidMigrationError(str(built))
        return built


_TEMPLATES: Final = _Templates()


def _built_template(mapping: EntityMapping, migrations: Sequence[Migration]) -> Database | InvalidMigrationError:
    template = _empty_database()
    if not migrations:
        mapping.metadata.create_all(template.engine, tables=mapping.tables)
        return template
    try:
        _migrate(template, mapping, migrations)
    except InvalidMigrationError as failure:  # every test on these migrations fails alike, with this cause
        template.close()
        return failure
    return template


def _migrate(template: Database, mapping: EntityMapping, migrations: Sequence[Migration]) -> None:
    """Runs `migrations` on `template`, then compares the schema with the entities; raises what does not fit."""
    schema = SchemaMigrations(template, migrations)
    try:
        schema.migrate()
    except DBAPIError as error:
        failed = next(iter(schema.pending()), None)
        name = failed.path.name if failed is not None else "A migration"
        raise InvalidMigrationError(
            f"{name} does not run on SQLite, the database in memory of a test: {error.orig}\n\n"
            f"    {error.statement}\n\n{_POSTGRESQL_HINT}"
        ) from error
    if missing := MigrationGenerator(template, mapping, schema).changes_sqlite_shows():
        raise InvalidMigrationError(
            "The migrations do not build the tables of the entities; make_migration would still write, in "
            f"PostgreSQL's SQL:\n\n{missing}"
        )
    _refuse_keys_sqlite_does_not_number(template, mapping)


def _refuse_keys_sqlite_does_not_number(template: Database, mapping: EntityMapping) -> None:
    # SQLite numbers the rows itself only for a key declared exactly INTEGER PRIMARY KEY: PostgreSQL's BIGSERIAL is a
    # type name like any other there, and the first save of an entity with a generated key would fail on its empty key.
    with template.engine.connect() as connection:
        for table in mapping.tables:
            numbered = [column.name for column in table.primary_key if column.autoincrement is True]
            declared = _declared_key(connection, table.name)
            if numbered and declared != dict.fromkeys(numbered, "INTEGER"):
                written = ", ".join(f"{name} {type_name}" for name, type_name in declared.items())
                raise InvalidMigrationError(
                    f"SQLite numbers the rows of {table.name} only for a key declared {numbered[0]} INTEGER PRIMARY "
                    f"KEY; the migrations declare {written}.\n\n{_POSTGRESQL_HINT}"
                )


def _declared_key(connection: Connection, table_name: str) -> dict[str, str]:
    """The columns of the primary key of `table_name`, with their type names as the migrations wrote them."""
    columns = connection.exec_driver_sql(f'PRAGMA table_info("{table_name}")').all()
    return {column.name: column.type.upper() for column in columns if column.pk}


def _sqlite3_of(connection: Connection) -> sqlite3.Connection:
    return cast("sqlite3.Connection", connection.connection.driver_connection)
