"""Foreign keys, unique constraints, unique and partial indexes, BIGINT and SMALLINT, as an existing schema has them.

The entities describe a schema with its own names, so the schema checks find nothing to change: on the SQLite in
memory of a test and on PostgreSQL alike, where each object does what it does in production. The tests on PostgreSQL
run it in a container and are skipped without a running Docker.
"""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import pytest

from snakeboot.data import (
    REPOSITORY_ATTRIBUTE,
    BigInt,
    DataIntegrityViolationError,
    ForeignKey,
    Id,
    InvalidEntityError,
    UniqueConstraint,
    entity,
)
from snakeboot.sqlalchemy_data import Database
from snakeboot.sqlalchemy_data.entity_mapping import EntityMapping
from snakeboot.sqlalchemy_data.migration_generator import MigrationGenerator
from snakeboot.sqlalchemy_data.schema_migrations import (
    InvalidMigrationError,
    Migration,
    SchemaMigrations,
    migrations_in,
)
from snakeboot.sqlalchemy_data.sqlalchemy_repository_operations import SqlAlchemyRepositoryOperations
from snakeboot.sqlalchemy_data.testing import in_memory_database, postgresql_database
from snakeboot.testing import PostgreSQLContainer
from tests.containers import docker_runs
from tests.data.funding_entities import (
    ENTITIES,
    SCHEMA,
    CallNoteRecord,
    CallNoteRecords,
    FundingCallRecord,
    FundingCallRecords,
    FundingDeadlineRecord,
    FundingDeadlineRecords,
    TemplateRecord,
    TemplateRecords,
)

IMAGE = PostgreSQLContainer().image

on_docker = pytest.mark.skipif(not docker_runs(), reason="a PostgreSQLContainer needs a running Docker")

SOURCE_URL = "https://example.org/call-template"

# Unlike the entities: an INTEGER budget, a unique index where they declare a unique constraint, and a foreign key
# they do not declare.
UNFIT_SCHEMA = """
CREATE TABLE fc_programme (id BIGINT NOT NULL PRIMARY KEY, name TEXT NOT NULL, budget INTEGER NOT NULL);
CREATE UNIQUE INDEX fc_programme_name_uniq ON fc_programme (name);
CREATE TABLE fc_programme_call (
    id BIGINT NOT NULL PRIMARY KEY,
    programme_id BIGINT NOT NULL REFERENCES fc_programme (id) ON DELETE CASCADE
);
"""


@entity("fc_programme", unique_constraints=(UniqueConstraint("fc_programme_name_uniq", "name"),))
@dataclass
class ProgrammeRecord:
    id: Annotated[int, Id(), BigInt()]
    name: str
    budget: Annotated[int, BigInt()]


@entity("fc_programme_call")
@dataclass
class ProgrammeCallRecord:
    id: Annotated[int, Id(), BigInt()]
    programme_id: Annotated[int, BigInt()]


@entity("fc_stray_reference")
@dataclass
class StrayReferenceRecord:
    id: Annotated[int, Id()]
    funding_call_id: Annotated[int, ForeignKey("fc_funding_call.number")]


def migrations(location: Path, sql: str = SCHEMA) -> Sequence[Migration]:
    location.mkdir(parents=True, exist_ok=True)
    (location / "V1__create_the_funding_calls.sql").write_text(sql, encoding="utf-8")
    return migrations_in([location])


def repository[R](interface: Callable[..., R], database: Database) -> R:
    operations = SqlAlchemyRepositoryOperations(database, EntityMapping.of(ENTITIES))
    implementation: R = getattr(interface, REPOSITORY_ATTRIBUTE)(operations)
    return implementation


@pytest.fixture(
    params=[
        "SQLite built by the migrations",
        "SQLite built from the entities",
        pytest.param("PostgreSQL built by the migrations", marks=on_docker),
    ]
)
def database(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Database]:
    if request.param == "SQLite built from the entities":
        database = in_memory_database(ENTITIES, migrations=[])
    elif request.param == "SQLite built by the migrations":
        database = in_memory_database(ENTITIES, migrations=migrations(tmp_path))
    else:
        database = postgresql_database(IMAGE, ENTITIES, migrations=migrations(tmp_path))
    yield database
    database.close()


def test_deleting_a_funding_call_deletes_its_deadlines(database: Database) -> None:
    calls, deadlines = repository(FundingCallRecords, database), repository(FundingDeadlineRecords, database)
    call = calls.save(FundingCallRecord(1, "researcher", "HORIZON-1"))
    deadlines.save_all([FundingDeadlineRecord(1, 1, 1), FundingDeadlineRecord(2, 1, 2)])

    calls.delete(call)

    assert deadlines.count() == 0


def test_a_funding_call_that_a_note_refers_to_is_not_deleted(database: Database) -> None:
    calls, notes = repository(FundingCallRecords, database), repository(CallNoteRecords, database)
    call = calls.save(FundingCallRecord(1, "researcher", "HORIZON-1"))
    notes.save(CallNoteRecord(1, 1, "ask the research office"))

    with pytest.raises(DataIntegrityViolationError):
        calls.delete(call)

    assert calls.count() == 1


def test_a_deadline_of_a_funding_call_that_does_not_exist_is_refused(database: Database) -> None:
    with pytest.raises(DataIntegrityViolationError):
        repository(FundingDeadlineRecords, database).save(FundingDeadlineRecord(1, 404, 1))


def test_a_second_funding_call_with_the_same_audience_and_reference_is_refused(database: Database) -> None:
    calls = repository(FundingCallRecords, database)
    calls.save(FundingCallRecord(1, "researcher", "HORIZON-1"))

    with pytest.raises(DataIntegrityViolationError):
        calls.save(FundingCallRecord(2, "researcher", "HORIZON-1"))


def test_a_partial_unique_index_holds_only_the_rows_of_its_condition(database: Database) -> None:
    templates = repository(TemplateRecords, database)
    templates.save_all(
        [
            TemplateRecord(uuid4(), SOURCE_URL, "written_by_hand"),
            TemplateRecord(uuid4(), SOURCE_URL, "written_by_hand"),
            TemplateRecord(uuid4(), SOURCE_URL, "found_at_source"),
        ]
    )

    with pytest.raises(DataIntegrityViolationError):
        templates.save(TemplateRecord(uuid4(), SOURCE_URL, "found_at_source"))


def test_a_big_int_holds_an_amount_past_two_billion(database: Database) -> None:
    calls = repository(FundingCallRecords, database)
    calls.save(FundingCallRecord(1, "kdg", "ERC-1", budget=5_000_000_000))

    found = calls.find_by_id(1)

    assert found is not None
    assert found.budget == 5_000_000_000


def test_on_sqlite_the_schema_of_the_migrations_fits_the_entities(tmp_path: Path) -> None:
    database = in_memory_database(ENTITIES, migrations=migrations(tmp_path))
    schema = SchemaMigrations(database, migrations(tmp_path))

    assert MigrationGenerator(database, EntityMapping.of(ENTITIES), schema).changes_sqlite_shows() == ""
    database.close()


def test_make_migration_writes_each_key_constraint_index_and_size_for_sqlite() -> None:
    empty = in_memory_database()

    sql = MigrationGenerator(empty, EntityMapping.of(ENTITIES), SchemaMigrations(empty, [])).changes()

    assert "CONSTRAINT fc_funding_call_audience_uniq UNIQUE (audience_kind, reference)" in sql
    assert (
        "CONSTRAINT fc_funding_deadline_call_fk FOREIGN KEY(funding_call_id) REFERENCES fc_funding_call (id) "
        "ON DELETE CASCADE"
    ) in sql
    assert (
        "CONSTRAINT fc_call_note_funding_call_id_fk FOREIGN KEY(funding_call_id) REFERENCES fc_funding_call (id) "
        "DEFERRABLE INITIALLY DEFERRED"
    ) in sql
    assert (
        "CREATE UNIQUE INDEX fc_template_source_url_uniq ON fc_template (source_url) WHERE origin = 'found_at_source';"
    ) in sql
    assert "budget BIGINT," in sql
    assert "stage SMALLINT NOT NULL," in sql
    empty.close()


@pytest.mark.parametrize(
    ("entity_types", "reference"),
    [
        pytest.param((FundingDeadlineRecord,), "fc_funding_call.id", id="a table no entity keeps"),
        pytest.param((FundingCallRecord, StrayReferenceRecord), "fc_funding_call.number", id="a column it lacks"),
    ],
)
def test_a_foreign_key_to_a_column_no_entity_has_stops_the_start(
    entity_types: tuple[type, ...], reference: str
) -> None:
    with pytest.raises(InvalidEntityError, match=f"refers to {reference}, a column of no entity"):
        EntityMapping.of(entity_types)


@on_docker
def test_on_postgresql_the_schema_of_the_migrations_fits_the_entities(tmp_path: Path) -> None:
    database = postgresql_database(IMAGE, ENTITIES, migrations=migrations(tmp_path))
    schema = SchemaMigrations(database, migrations(tmp_path))

    assert MigrationGenerator(database, EntityMapping.of(ENTITIES), schema).changes() == ""
    database.close()


@on_docker
def test_make_migration_writes_each_key_constraint_index_and_size_for_postgresql(tmp_path: Path) -> None:
    empty = postgresql_database(IMAGE, [], migrations=[])
    generator = MigrationGenerator(empty, EntityMapping.of(ENTITIES), SchemaMigrations(empty, []))

    path = generator.write("create the funding calls", generator.changes(), into=tmp_path)

    sql = path.read_text(encoding="utf-8")
    assert "CONSTRAINT fc_funding_call_audience_uniq UNIQUE (audience_kind, reference)" in sql
    assert (
        "CONSTRAINT fc_funding_deadline_call_fk FOREIGN KEY(funding_call_id) REFERENCES fc_funding_call (id) "
        "ON DELETE CASCADE"
    ) in sql
    assert (
        "CONSTRAINT fc_call_note_funding_call_id_fk FOREIGN KEY(funding_call_id) REFERENCES fc_funding_call (id) "
        "DEFERRABLE INITIALLY DEFERRED"
    ) in sql
    assert (
        "CREATE UNIQUE INDEX fc_template_source_url_uniq ON fc_template (source_url) WHERE origin = 'found_at_source';"
    ) in sql
    assert "budget BIGINT," in sql
    assert "stage SMALLINT NOT NULL," in sql
    migrated = SchemaMigrations(empty, migrations_in([tmp_path]))
    migrated.migrate()
    assert MigrationGenerator(empty, EntityMapping.of(ENTITIES), migrated).changes() == ""
    empty.close()


@on_docker
# Alembic warns so whenever it writes ALTER COLUMN ... TYPE for PostgreSQL; the SQL is right.
@pytest.mark.filterwarnings("ignore:autoincrement and existing_autoincrement only make sense for MySQL")
def test_on_postgresql_a_key_a_constraint_or_a_size_unlike_the_schema_stops_the_tests(tmp_path: Path) -> None:
    with pytest.raises(InvalidMigrationError) as stopped:
        postgresql_database(
            IMAGE, [ProgrammeRecord, ProgrammeCallRecord], migrations=migrations(tmp_path, UNFIT_SCHEMA)
        )

    # Without ForeignKey(...) on the entity, make_migration would drop the key the migration made.
    assert "ALTER TABLE fc_programme_call DROP CONSTRAINT fc_programme_call_programme_id_fkey;" in str(stopped.value)
    assert "DROP INDEX fc_programme_name_uniq;" in str(stopped.value)
    assert "ALTER TABLE fc_programme ADD CONSTRAINT fc_programme_name_uniq UNIQUE (name);" in str(stopped.value)
    assert "ALTER TABLE fc_programme ALTER COLUMN budget TYPE BIGINT;" in str(stopped.value)
