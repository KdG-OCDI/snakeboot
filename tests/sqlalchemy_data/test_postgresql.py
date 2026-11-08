"""On PostgreSQL: generated migrations, JSONB, row locks and a pgvector search.

Set SNAKEBOOT_TEST_POSTGRESQL_URL to a database these tests may fill and empty, such as one of
`docker run -e POSTGRES_PASSWORD=snakeboot -p 55432:5432 pgvector/pgvector:pg17`:

    SNAKEBOOT_TEST_POSTGRESQL_URL=postgresql+psycopg://postgres:snakeboot@localhost:55432/postgres
"""

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Protocol

import pytest
from sqlalchemy import create_engine, text

from snakeboot.data import REPOSITORY_ATTRIBUTE, CrudRepository, Id, Vector, entity, query
from snakeboot.sqlalchemy_data import Database
from snakeboot.sqlalchemy_data.entity_mapping import EntityMapping
from snakeboot.sqlalchemy_data.migration_generator import MigrationGenerator
from snakeboot.sqlalchemy_data.schema_migrations import HISTORY_TABLE, SchemaMigrations, migrations_in
from snakeboot.sqlalchemy_data.sqlalchemy_repository_operations import SqlAlchemyRepositoryOperations
from tests.data.sample_entities import GameRecord, PlayedMoveRecord

URL = os.environ.get("SNAKEBOOT_TEST_POSTGRESQL_URL", "")

pytestmark = pytest.mark.skipif(not URL, reason="SNAKEBOOT_TEST_POSTGRESQL_URL names no PostgreSQL")


@entity("pg_knowledge_chunk")
@dataclass
class ChunkRecord:
    id: Annotated[int | None, Id(generated=True)]
    scope: str
    embedding: Annotated[list[float], Vector(3)]


@dataclass
class Retrieved:
    scope: str
    distance: float


class ChunkRecords(CrudRepository[ChunkRecord, int], Protocol):
    @query(
        "SELECT scope, embedding <=> CAST(:embedding AS vector) AS distance FROM pg_knowledge_chunk "
        "WHERE scope = ANY(:scopes) ORDER BY distance LIMIT :limit"
    )
    def search(self, embedding: list[float], scopes: list[str], limit: int) -> list[Retrieved]: ...


ENTITIES = (GameRecord, ChunkRecord, PlayedMoveRecord)


@pytest.fixture
def database() -> Iterator[Database]:
    database = Database(create_engine(URL))
    with database.transaction() as session:
        session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        for table in ("data_game", "data_played_move", "pg_knowledge_chunk", HISTORY_TABLE):
            session.execute(text(f"DROP TABLE IF EXISTS {table}"))
    yield database
    database.close()


def generator_for(database: Database, location: Path) -> MigrationGenerator:
    mapping = EntityMapping.of(ENTITIES)
    return MigrationGenerator(database, mapping, SchemaMigrations(database, migrations_in([location])))


def test_make_migration_writes_the_schema_of_the_entities_as_plain_sql(database: Database, tmp_path: Path) -> None:
    generator = generator_for(database, tmp_path)

    path = generator.write("create the games", generator.changes(), into=tmp_path)

    sql = path.read_text(encoding="utf-8")
    assert path.name == "V1__create_the_games.sql"
    assert "CREATE TABLE data_game" in sql
    assert "board JSONB NOT NULL" in sql
    assert "embedding VECTOR(3) NOT NULL" in sql
    assert "move JSONB NOT NULL" in sql
    assert "best_move JSONB," in sql
    assert all(line == line.rstrip() for line in sql.splitlines())


def test_after_migrate_the_schema_fits_the_entities(database: Database, tmp_path: Path) -> None:
    generator = generator_for(database, tmp_path)
    generator.write("create the games", generator.changes(), into=tmp_path)

    SchemaMigrations(database, migrations_in([tmp_path])).migrate()

    assert generator_for(database, tmp_path).changes() == ""


def test_a_vector_search_runs_its_sql_with_arrays(database: Database, tmp_path: Path) -> None:
    generator = generator_for(database, tmp_path)
    generator.write("create the chunks", generator.changes(), into=tmp_path)
    SchemaMigrations(database, migrations_in([tmp_path])).migrate()
    operations = SqlAlchemyRepositoryOperations(database, EntityMapping.of(ENTITIES))
    chunks: ChunkRecords = getattr(ChunkRecords, REPOSITORY_ATTRIBUTE)(operations)
    chunks.save_all(
        [
            ChunkRecord(None, "rules", [1, 0, 0]),
            ChunkRecord(None, "rules", [0, 1, 0]),
            ChunkRecord(None, "x", [1, 0, 0]),
        ]
    )

    found = chunks.search([1.0, 0.1, 0.0], ["rules"], limit=1)

    assert [(hit.scope, round(hit.distance, 3)) for hit in found] == [("rules", 0.005)]
