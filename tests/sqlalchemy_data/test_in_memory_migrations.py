"""The database in memory of a test holds the schema the migrations build, once per process, copied for every test.

The migrations here are written for PostgreSQL, as an application's are: SQLite takes their type names as they come.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from uuid import UUID

import pytest
from sqlalchemy import inspect, text

from snakeboot.data import Column, DataIntegrityViolationError, Id, entity
from snakeboot.sqlalchemy_data import Database
from snakeboot.sqlalchemy_data.schema_migrations import HISTORY_TABLE, InvalidMigrationError, migrations_in
from snakeboot.sqlalchemy_data.testing import in_memory_database

# Unlike the entity: no NOT NULL on the key, which PostgreSQL implies; TEXT for its VARCHAR(40); a check of its own.
CRATE = """
CREATE TABLE crate (
    crate_id UUID PRIMARY KEY,
    label TEXT NOT NULL,
    CONSTRAINT crate_label_check CHECK (label <> '')
);
"""


@entity("crate")
@dataclass
class CrateRecord:
    crate_id: Annotated[UUID, Id()]
    label: Annotated[str, Column(length=40)]


@entity("pallet")
@dataclass
class PalletRecord:
    pallet_id: Annotated[int | None, Id(generated=True)]
    label: str


def migrations(location: Path, **scripts: str) -> Path:
    location.mkdir(parents=True, exist_ok=True)
    for name, sql in scripts.items():
        (location / f"{name}.sql").write_text(sql, encoding="utf-8")
    return location


def tables_of(database: Database) -> set[str]:
    return set(inspect(database.engine).get_table_names())


@pytest.fixture
def crates(tmp_path: Path) -> Iterator[Database]:
    database = in_memory_database(
        [CrateRecord], migrations=migrations_in([migrations(tmp_path, V1__create_crate=CRATE)])
    )
    yield database
    database.close()


def test_the_migrations_build_the_schema_with_what_only_they_declare(crates: Database) -> None:
    assert tables_of(crates) == {"crate", HISTORY_TABLE}
    with pytest.raises(DataIntegrityViolationError), crates.transaction() as session:
        session.execute(text("INSERT INTO crate (crate_id, label) VALUES ('a', '')"))


def test_every_database_is_a_copy_of_its_own(crates: Database, tmp_path: Path) -> None:
    with crates.transaction() as session:
        session.execute(text("INSERT INTO crate (crate_id, label) VALUES ('a', 'apples')"))

    other = in_memory_database([CrateRecord], migrations=migrations_in([tmp_path]))
    with other.session() as session:
        assert session.execute(text("SELECT COUNT(*) FROM crate")).scalar_one() == 0
    other.close()


def test_without_migrations_the_tables_come_from_the_entities() -> None:
    database = in_memory_database([CrateRecord], migrations=[])

    assert tables_of(database) == {"crate"}
    database.close()


def test_without_entities_the_database_is_empty() -> None:
    database = in_memory_database()

    assert tables_of(database) == set()
    database.close()


def test_a_migration_that_sqlite_rejects_stops_the_start_with_its_name(tmp_path: Path) -> None:
    scripts = migrations(
        tmp_path, V1__create_crate=CRATE, V2__widen_the_label="ALTER TABLE crate ALTER label TYPE TEXT;"
    )

    with pytest.raises(InvalidMigrationError, match=r"(?s)V2__widen_the_label\.sql does not run on SQLite.*Container"):
        in_memory_database([CrateRecord], migrations=migrations_in([scripts]))


def test_migrations_that_lack_a_column_stop_the_start_with_the_sql_it_needs(tmp_path: Path) -> None:
    scripts = migrations(tmp_path, V1__create_crate="CREATE TABLE crate (crate_id UUID NOT NULL PRIMARY KEY);")

    with pytest.raises(InvalidMigrationError, match="ALTER TABLE crate ADD COLUMN label VARCHAR"):
        in_memory_database([CrateRecord], migrations=migrations_in([scripts]))


def test_a_generated_key_that_sqlite_would_not_number_stops_the_start(tmp_path: Path) -> None:
    pallet = "CREATE TABLE pallet (pallet_id BIGSERIAL NOT NULL, label TEXT NOT NULL, PRIMARY KEY (pallet_id));"
    scripts = migrations(tmp_path, V1__create_pallet=pallet)

    with pytest.raises(InvalidMigrationError, match="declare pallet_id BIGSERIAL"):
        in_memory_database([PalletRecord], migrations=migrations_in([scripts]))


def test_a_generated_key_declared_integer_primary_key_is_numbered(tmp_path: Path) -> None:
    pallet = "CREATE TABLE pallet (pallet_id INTEGER NOT NULL, label TEXT NOT NULL, PRIMARY KEY (pallet_id));"
    database = in_memory_database([PalletRecord], migrations=migrations_in([migrations(tmp_path, V1__pallet=pallet)]))

    with database.transaction() as session:
        session.execute(text("INSERT INTO pallet (label) VALUES ('apples')"))
        assert session.execute(text("SELECT pallet_id FROM pallet")).scalar_one() == 1
    database.close()
