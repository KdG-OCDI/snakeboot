from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

DEFAULT_POSTGRESQL_IMAGE: Final = "postgres:17-alpine"


@dataclass(frozen=True, slots=True)
class PostgreSQLContainer:
    """A PostgreSQL in a container of Docker for the tests, like Testcontainers' `PostgreSQLContainer`.

    One container serves every test of the process that asks for its image. The application's own migrations run
    once, in a database that every test then copies (PostgreSQL's `CREATE DATABASE ... TEMPLATE`), so a test starts
    on the schema production has, in a database of its own, within a tenth of a second. Before that, the migrated
    schema is compared with the entities, like Hibernate's `ddl-auto=validate`: a change that `make_migration` would
    still write stops the tests. Any PostgreSQL image will do: `pgvector/pgvector:pg17` for a `Vector`.

    It needs a running Docker and `snakeboot[testcontainers]`.
    """

    image: str = DEFAULT_POSTGRESQL_IMAGE


@dataclass(frozen=True, slots=True)
class TestEnvironment:
    """Where a test runs its application, like Spring's `Environment` of a test: profile, properties and database.

    `profile` activates a profile, like `@ActiveProfiles`, whatever SNAKEBOOT_PROFILE says. `properties` win over the
    files and the environment, like `@SpringBootTest(properties = ...)`: `{"scheduling.auto_startup": False}`.
    `database` is a `PostgreSQLContainer`, or None for a fresh SQLite in memory whose tables come from the entities.
    """

    __test__ = False  # pytest: a class named Test... that is no test class

    profile: str | None = None
    properties: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))
    database: PostgreSQLContainer | None = None
