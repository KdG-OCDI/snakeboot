"""On PostgreSQL in a container: `migrate` baselines a schema that another tool made, keeps its data and leaves it as
the entities describe it; a fresh database runs the script of that schema instead and gets the same.

The schema is written as `pg_dump --schema-only` writes it. Without a running Docker these tests are skipped.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from snakeboot.data import Column, DataIntegrityViolationError, Id, Index, entity
from snakeboot.sqlalchemy_data import Database
from snakeboot.sqlalchemy_data.entity_mapping import EntityMapping
from snakeboot.sqlalchemy_data.migration_generator import MigrationGenerator
from snakeboot.sqlalchemy_data.schema_migrations import (
    BASELINE_CHECKSUM,
    HISTORY_TABLE,
    SchemaMigrations,
    migrations_in,
)
from snakeboot.sqlalchemy_data.testing import postgresql_database
from snakeboot.testing import PostgreSQLContainer
from tests.containers import docker_runs

pytestmark = pytest.mark.skipif(not docker_runs(), reason="a PostgreSQL in a container needs a running Docker")

POSTGRESQL = PostgreSQLContainer()

SCHEMA_BEFORE_SNAKEBOOT = """CREATE TABLE public.funding_call (
    id uuid NOT NULL,
    title character varying(200) NOT NULL,
    places integer NOT NULL,
    CONSTRAINT funding_call_places_check CHECK ((places >= 0))
);

ALTER TABLE ONLY public.funding_call
    ADD CONSTRAINT funding_call_pkey PRIMARY KEY (id);

CREATE INDEX funding_call_title_idx ON public.funding_call USING btree (title);
"""

ADD_A_BUDGET = "ALTER TABLE funding_call ADD COLUMN budget INTEGER;\n"


@entity("funding_call", indexes=(Index("funding_call_title_idx", "title"),))
@dataclass
class FundingCallRecord:
    id: Annotated[UUID, Id()]
    title: Annotated[str, Column(length=200)]
    places: int
    budget: int | None = None


@pytest.fixture
def database() -> Iterator[Database]:
    """A database of its own on the container's PostgreSQL, without the history table of its template."""
    database = postgresql_database(POSTGRESQL.image, [])
    with database.engine.begin() as connection:
        connection.exec_driver_sql(f"DROP TABLE {HISTORY_TABLE}")
    yield database
    database.close()


@pytest.fixture
def scripts(tmp_path: Path) -> Path:
    (tmp_path / "V1__schema_before_snakeboot.sql").write_text(SCHEMA_BEFORE_SNAKEBOOT, encoding="utf-8")
    (tmp_path / "V2__add_a_budget.sql").write_text(ADD_A_BUDGET, encoding="utf-8")
    return tmp_path


def fits_the_entities(database: Database, schema: SchemaMigrations) -> bool:
    return MigrationGenerator(database, EntityMapping.of([FundingCallRecord]), schema).changes() == ""


def test_migrate_baselines_a_schema_made_before_the_migrations_and_keeps_its_data(
    database: Database, scripts: Path
) -> None:
    with database.engine.begin() as connection:
        connection.exec_driver_sql(SCHEMA_BEFORE_SNAKEBOOT)
        connection.execute(
            text("INSERT INTO funding_call (id, title, places) VALUES (:id, 'Horizon', 3)"), {"id": uuid4()}
        )
    schema = SchemaMigrations(database, migrations_in([scripts]), baseline_version="1")

    result = schema.migrate()  # had V1 run, its CREATE TABLE would have failed on the table that is there

    assert ([m.label for m in result.baselined], [m.label for m in result.applied]) == (["1"], ["2"])
    with database.session() as session:
        history = session.execute(text(f"SELECT version, checksum FROM {HISTORY_TABLE} ORDER BY version")).all()
        kept = session.execute(text("SELECT title, places, budget FROM funding_call")).one()
    assert [tuple(row) for row in history] == [("1", BASELINE_CHECKSUM), ("2", result.applied[0].checksum)]
    assert tuple(kept) == ("Horizon", 3, None)
    assert fits_the_entities(database, schema)


def test_a_fresh_database_runs_the_script_of_that_schema_and_gets_the_same(database: Database, scripts: Path) -> None:
    schema = SchemaMigrations(database, migrations_in([scripts]), baseline_version="1")

    result = schema.migrate()

    assert ([m.label for m in result.baselined], [m.label for m in result.applied]) == ([], ["1", "2"])
    assert fits_the_entities(database, schema)
    with pytest.raises(DataIntegrityViolationError, match="funding_call_places_check"), database.session() as session:
        session.execute(text("INSERT INTO funding_call (id, title, places) VALUES (:id, 'x', -1)"), {"id": uuid4()})


PG_DUMP_PREAMBLE = """SET statement_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET client_min_messages = warning;
"""


def test_a_script_as_pg_dump_writes_it_leaves_no_setting_behind(database: Database, tmp_path: Path) -> None:
    # pg_dump's preamble empties search_path for the rest of the session: the history row, and V2, which names
    # funding_call without its schema, would no longer find their tables.
    (tmp_path / "V1__schema_before_snakeboot.sql").write_text(PG_DUMP_PREAMBLE + SCHEMA_BEFORE_SNAKEBOOT, "utf-8")
    (tmp_path / "V2__add_a_budget.sql").write_text(ADD_A_BUDGET, encoding="utf-8")
    schema = SchemaMigrations(database, migrations_in([tmp_path]), baseline_version=None)

    result = schema.migrate()

    assert [m.label for m in result.applied] == ["1", "2"]
    assert fits_the_entities(database, schema)


def test_a_percent_sign_in_a_script_is_a_percent_sign(database: Database, tmp_path: Path) -> None:
    # Not the start of a placeholder: in a comment, in a LIKE, in a default.
    (tmp_path / "V1__codes.sql").write_text(
        "-- 100% of the codes start with C\n"
        "CREATE TABLE code (value VARCHAR(10) NOT NULL CHECK (value LIKE 'C%'), note TEXT DEFAULT '50%');\n",
        encoding="utf-8",
    )
    schema = SchemaMigrations(database, migrations_in([tmp_path]), baseline_version=None)

    assert [m.label for m in schema.migrate().applied] == ["1"]
    with pytest.raises(DataIntegrityViolationError), database.session() as session:
        session.execute(text("INSERT INTO code (value) VALUES ('D1')"))
