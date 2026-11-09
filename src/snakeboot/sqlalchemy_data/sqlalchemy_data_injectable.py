"""Registers the database, the transactions, the repositories' operations and the migrations with wireup.

`snakeboot.boot` adds this module, and `migration_commands`, to the container only when the application has a
`[database]` section, like Spring Boot's `DataSourceAutoConfiguration` with its conditions: an application without
the section imports no SQLAlchemy.
"""

from collections.abc import Iterator

from wireup import injectable

from snakeboot.actuator import HealthIndicator
from snakeboot.configuration import DatabaseProperties
from snakeboot.data import ENTITY_ATTRIBUTE, RepositoryOperations
from snakeboot.lifecycle.application_components import ApplicationComponents
from snakeboot.sqlalchemy_data.database import Database
from snakeboot.sqlalchemy_data.database_health_indicator import DatabaseHealthIndicator
from snakeboot.sqlalchemy_data.entity_mapping import EntityMapping
from snakeboot.sqlalchemy_data.migration_generator import MigrationGenerator
from snakeboot.sqlalchemy_data.schema_migrations import SchemaMigrations, migration_locations, migrations_in
from snakeboot.sqlalchemy_data.sqlalchemy_repository_operations import SqlAlchemyRepositoryOperations
from snakeboot.sqlalchemy_data.sqlalchemy_transaction_manager import SqlAlchemyTransactionManager
from snakeboot.transaction import TransactionManager


@injectable
def database(properties: DatabaseProperties) -> Iterator[Database]:
    """Provides the PostgreSQL database of `[database]`, and closes its connections when the container closes."""
    opened = Database.of(properties)
    yield opened
    opened.close()


@injectable(as_type=HealthIndicator, qualifier="snakeboot.sqlalchemy_data.DatabaseHealthIndicator")
def database_health_indicator(database: Database) -> HealthIndicator:
    """Provides the check of the database that `/health` runs."""
    return DatabaseHealthIndicator(database)


@injectable
def entity_mapping(components: ApplicationComponents) -> EntityMapping:
    """Maps every `@entity` of the component scan to its table."""
    return EntityMapping.of(components.classes_marked(ENTITY_ATTRIBUTE))


@injectable(as_type=TransactionManager)
def transaction_manager(database: Database) -> TransactionManager:
    """Provides the transaction manager that `@transactional` runs on."""
    return SqlAlchemyTransactionManager(database)


@injectable(as_type=RepositoryOperations)
def repository_operations(database: Database, mapping: EntityMapping) -> RepositoryOperations:
    """Provides what every repository runs its queries with."""
    return SqlAlchemyRepositoryOperations(database, mapping)


@injectable
def schema_migrations(database: Database, mapping: EntityMapping) -> SchemaMigrations:
    """Provides the SQL migrations in the migrations directories next to the entities."""
    return SchemaMigrations(database, migrations_in(migration_locations(mapping.entity_types)))


@injectable
def migration_generator(database: Database, mapping: EntityMapping, migrations: SchemaMigrations) -> MigrationGenerator:
    """Provides what `make_migration` writes the next migration with."""
    return MigrationGenerator(database, mapping, migrations)
