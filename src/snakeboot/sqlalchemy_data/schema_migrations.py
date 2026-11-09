import hashlib
import logging
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from sqlalchemy import Column, Connection, MetaData, String, Table, select, text

from snakeboot.sqlalchemy_data.database import Database
from snakeboot.sqlalchemy_data.entity_mapping import AwareDateTime

logger = logging.getLogger(__name__)

LOCATION: Final = "migrations"
"""The directory, next to the module of an entity, that holds the SQL migrations of its tables."""

HISTORY_TABLE: Final = "snakeboot_schema_history"
"""The table that remembers which migrations ran, like Flyway's `flyway_schema_history`."""

MIGRATION_FILE: Final = re.compile(r"V(?P<version>\d+(?:_\d+)*)__(?P<description>[A-Za-z0-9_]+)\.sql")
"""`V1__create_games.sql`, `V2_1__add_an_index.sql`: a version, two underscores, a description, as in Flyway."""

_MIGRATION_LOCK: Final = 4_242_424_242
"""PostgreSQL's advisory lock that keeps two processes from migrating one database at the same time."""

_HISTORY: Final = Table(
    HISTORY_TABLE,
    MetaData(),
    Column("version", String(50), primary_key=True),
    Column("description", String(200), nullable=False),
    Column("script", String(1000), nullable=False),
    Column("checksum", String(64), nullable=False),
    Column("installed_on", AwareDateTime(), nullable=False),
)


class InvalidMigrationError(RuntimeError):
    """Raised when the migrations cannot run: a name that is no version, two scripts for one version, a script that
    changed after it ran, or a version the database ran that no script has."""


@dataclass(frozen=True, slots=True)
class Migration:
    """One SQL script that changes the schema, read from a migrations directory."""

    version: tuple[int, ...]
    description: str
    path: Path

    @property
    def label(self) -> str:
        """`1`, or `2.1`: the version as the history table writes it."""
        return ".".join(str(part) for part in self.version)

    @property
    def sql(self) -> str:
        """The script, with Unix line ends whatever the checkout wrote."""
        return self.path.read_text(encoding="utf-8").replace("\r\n", "\n")

    @property
    def checksum(self) -> str:
        """The SHA-256 of the script: a script that changed after it ran stops the next `migrate`."""
        return hashlib.sha256(self.sql.encode()).hexdigest()


LIBRARY_PACKAGE: Final = "snakeboot"
"""The package whose own entities (the event publication registry's, the scheduler lock's) have no migrations of
their own: `make_migration` writes their tables into the application's migrations, which `migrate` runs."""


def migration_locations(entity_types: Iterable[type]) -> list[Path]:
    """Returns the migrations directory next to the module of each of the application's entities, whether it exists
    yet or not; snakeboot's own entities have none."""
    modules = {
        sys.modules[entity_type.__module__]
        for entity_type in entity_types
        if entity_type.__module__.partition(".")[0] != LIBRARY_PACKAGE
    }
    return sorted({Path(module.__file__ or "").parent / LOCATION for module in modules})


def migrations_in(locations: Iterable[Path]) -> list[Migration]:
    """Returns every migration in `locations`, by version; a wrong name or a version written twice stops the start."""
    found: dict[tuple[int, ...], Migration] = {}
    for path in sorted(path for location in locations if location.is_dir() for path in location.glob("*.sql")):
        named = MIGRATION_FILE.fullmatch(path.name)
        if named is None:
            raise InvalidMigrationError(f"{path}: a migration is named V<version>__<description>.sql.")
        migration = Migration(tuple(int(part) for part in named["version"].split("_")), named["description"], path)
        if (earlier := found.get(migration.version)) is not None:
            raise InvalidMigrationError(f"Two migrations have version {migration.label}: {earlier.path} and {path}.")
        found[migration.version] = migration
    return [found[version] for version in sorted(found)]


class SchemaMigrations:
    """Brings a database's schema up to date with SQL scripts, like Flyway in Spring Boot.

    Each script runs once, in version order, in a transaction of its own, and the history table remembers it with its
    checksum. On PostgreSQL an advisory lock lets one process migrate while another waits, so two replicas that start
    together do not both run a script.
    """

    def __init__(self, database: Database, migrations: Sequence[Migration]) -> None:
        self._database = database
        self._migrations = migrations

    @property
    def migrations(self) -> Sequence[Migration]:
        """Every migration the application has, by version."""
        return self._migrations

    def pending(self) -> list[Migration]:
        """Returns the migrations the database has not run, after checking the ones it has."""
        with self._database.engine.connect() as connection:
            return self._checked_pending(connection)

    def migrate(self) -> list[Migration]:
        """Runs every pending migration and returns them; a failing script stops the run and leaves no trace."""
        with self._database.engine.connect() as connection:
            self._lock(connection)
            pending = self._checked_pending(connection)
            for migration in pending:
                with connection.begin():
                    _execute_script(connection, migration.sql)
                    connection.execute(_HISTORY.insert().values(_history_row(migration)))
                logger.info("Applied migration V%s__%s", migration.label, migration.description)
            return pending

    def _checked_pending(self, connection: Connection) -> list[Migration]:
        with connection.begin():
            _HISTORY.create(connection, checkfirst=True)
            applied = dict(connection.execute(select(_HISTORY.c.version, _HISTORY.c.checksum)).all())
        known = {migration.label: migration for migration in self._migrations}
        for version, checksum in applied.items():
            _refuse_unknown_or_changed(version, checksum, known.get(version))
        return [migration for migration in self._migrations if migration.label not in applied]

    def _lock(self, connection: Connection) -> None:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _MIGRATION_LOCK})
            connection.commit()


def _refuse_unknown_or_changed(version: str, checksum: str, migration: Migration | None) -> None:
    if migration is None:
        raise InvalidMigrationError(f"The database ran migration {version}, which no migrations directory holds.")
    if migration.checksum != checksum:
        raise InvalidMigrationError(
            f"{migration.path} changed after it ran: write a new migration instead of changing one that ran."
        )


def _history_row(migration: Migration) -> dict[str, object]:
    return {
        "version": migration.label,
        "description": migration.description,
        "script": migration.path.name,
        "checksum": migration.checksum,
        "installed_on": datetime.now(UTC),
    }


def _execute_script(connection: Connection, sql: str) -> None:
    # PostgreSQL runs a script of several statements at once; Python's sqlite3, in the tests, only as a script.
    if connection.dialect.name == "sqlite":
        connection.connection.driver_connection.executescript(sql)  # type: ignore[union-attr]
    else:
        connection.exec_driver_sql(sql)
