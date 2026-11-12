import atexit
import hashlib
import threading
from collections.abc import Iterable, Sequence
from typing import Final, override
from uuid import uuid4

from sqlalchemy import URL, create_engine, make_url, text
from sqlalchemy.pool import NullPool

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

_SERVERS: Final[dict[str, "_PostgreSQLServer"]] = {}
_SERVERS_LOCK: Final = threading.Lock()


class ContainerUnavailableError(RuntimeError):
    """Raised when the PostgreSQL of a test cannot start: Docker is not running, or Testcontainers is missing."""


def postgresql_database(image: str, entity_types: Iterable[type]) -> Database:
    """Returns a fresh database on the PostgreSQL in a container of `image`, built by the application's migrations.

    The container starts with the first test that asks for `image` and stops when the process ends. The migrations of
    `entity_types` run once, in a template database that is then compared with the entities: when `make_migration`
    would still write something, every test on it stops with that SQL (`InvalidMigrationError`). Every test gets a
    copy of the template; closing the database drops the copy.
    """
    server = _server_of(image)
    return server.copy_of(server.template_for(EntityMapping.of(entity_types)))


def _server_of(image: str) -> "_PostgreSQLServer":
    with _SERVERS_LOCK:
        if image not in _SERVERS:
            _SERVERS[image] = _PostgreSQLServer.start(image)
        return _SERVERS[image]


class _PostgreSQLServer:
    """One PostgreSQL in a container, with a template database per set of migrations and a copy per test."""

    def __init__(self, url: URL) -> None:
        self._url = url
        self._admin = create_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
        self._templates: dict[str, str | InvalidMigrationError] = {}
        self._lock = threading.Lock()

    @classmethod
    def start(cls, image: str) -> "_PostgreSQLServer":
        try:
            from testcontainers.community.postgres import PostgresContainer  # noqa: PLC0415  # reason: only a test on PostgreSQL needs it
        except ImportError as error:
            raise ContainerUnavailableError(
                "A PostgreSQLContainer needs Testcontainers: install snakeboot[testcontainers]."
            ) from error
        container = PostgresContainer(image, driver="psycopg")
        try:
            container.start()
        except Exception as error:  # Docker fails differently per platform; each failure means no PostgreSQL
            raise ContainerUnavailableError(f"Docker did not start {image}; is Docker running? {error}") from error
        atexit.register(container.stop)
        return cls(make_url(container.get_connection_url()))

    def template_for(self, mapping: EntityMapping) -> str:
        """Returns the template database the migrations of `mapping` built, building it the first time."""
        migrations = migrations_in(migration_locations(mapping.entity_types))
        key = _fingerprint(mapping, migrations)
        with self._lock:
            if key not in self._templates:
                self._templates[key] = self._built_template(f"template_{key}", mapping, migrations)
            built = self._templates[key]
        if isinstance(built, InvalidMigrationError):
            raise InvalidMigrationError(str(built))
        return built

    def copy_of(self, template: str) -> Database:
        """Returns a database of its own for one test, copied from `template`."""
        name = f"test_{uuid4().hex}"
        self._execute(f'CREATE DATABASE "{name}" TEMPLATE "{template}"')
        return _CopiedDatabase(self, name)

    def url_of(self, name: str) -> URL:
        """Returns the URL of the database `name` on this server."""
        return self._url.set(database=name)

    def drop(self, name: str) -> None:
        """Drops the database `name`, whoever is still connected to it."""
        self._execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')

    def _built_template(
        self, name: str, mapping: EntityMapping, migrations: Sequence[Migration]
    ) -> str | InvalidMigrationError:
        self._execute(f'CREATE DATABASE "{name}"')
        failure = self._migration_failure(name, mapping, migrations)
        if failure is None:
            return name
        self.drop(name)
        return failure

    def _migration_failure(
        self, name: str, mapping: EntityMapping, migrations: Sequence[Migration]
    ) -> InvalidMigrationError | None:
        """Migrates the database `name` and compares it with the entities; returns what went wrong, or None."""
        database = Database(create_engine(self.url_of(name), poolclass=NullPool))
        try:
            schema = SchemaMigrations(database, migrations)
            schema.migrate()
            missing = MigrationGenerator(database, mapping, schema).changes()
        except Exception as error:  # noqa: BLE001  # reason: every test on these migrations fails alike, with this cause
            return InvalidMigrationError(f"The migrations failed on PostgreSQL: {error}")
        finally:
            database.close()
        if missing:
            return InvalidMigrationError(
                "The migrations do not build the tables of the entities; make_migration would still write:\n\n"
                + missing
            )
        return None

    def _execute(self, statement: str) -> None:
        with self._admin.connect() as connection:
            connection.execute(text(statement))


class _CopiedDatabase(Database):
    """The copy of a template that one test runs on; closing it drops the copy."""

    def __init__(self, server: _PostgreSQLServer, name: str) -> None:
        super().__init__(create_engine(server.url_of(name)))
        self._server = server
        self._name = name

    @override
    def close(self) -> None:
        super().close()
        self._server.drop(self._name)


def _fingerprint(mapping: EntityMapping, migrations: Sequence[Migration]) -> str:
    entities = [f"{entity_type.__module__}.{entity_type.__qualname__}" for entity_type in mapping.entity_types]
    scripts = [f"{migration.label}:{migration.checksum}" for migration in migrations]
    return hashlib.sha256("\n".join([*entities, *scripts]).encode()).hexdigest()[:16]
