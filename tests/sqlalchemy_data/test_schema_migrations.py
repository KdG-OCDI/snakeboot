"""SQL migrations run once each, in version order, and a script that changed after it ran stops the next run."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from snakeboot.sqlalchemy_data import Database
from snakeboot.sqlalchemy_data.schema_migrations import (
    HISTORY_TABLE,
    InvalidMigrationError,
    MigrateResult,
    SchemaMigrations,
    migration_locations,
    migrations_in,
)
from snakeboot.sqlalchemy_data.testing import in_memory_database
from tests.data.sample_entities import GameRecord


@pytest.fixture
def database() -> Iterator[Database]:
    database = in_memory_database()
    yield database
    database.close()


def write(location: Path, name: str, sql: str) -> Path:
    location.mkdir(parents=True, exist_ok=True)
    path = location / name
    path.write_bytes(sql.encode())
    return path


def tables_of(database: Database) -> set[str]:
    return set(inspect(database.engine).get_table_names())


def test_the_migrations_are_read_in_the_order_of_their_versions(tmp_path: Path) -> None:
    write(tmp_path, "V10__last.sql", "")
    write(tmp_path, "V2__second.sql", "")
    write(tmp_path, "V2_1__between.sql", "")

    assert [migration.label for migration in migrations_in([tmp_path])] == ["2", "2.1", "10"]


def test_a_script_that_is_no_migration_stops_the_start(tmp_path: Path) -> None:
    write(tmp_path, "create_games.sql", "")

    with pytest.raises(InvalidMigrationError, match=r"V<version>__<description>\.sql"):
        migrations_in([tmp_path])


def test_two_scripts_for_one_version_stop_the_start(tmp_path: Path) -> None:
    write(tmp_path / "a", "V1__games.sql", "")
    write(tmp_path / "b", "V1__moves.sql", "")

    with pytest.raises(InvalidMigrationError, match="Two migrations have version 1"):
        migrations_in([tmp_path / "a", tmp_path / "b"])


def test_the_migrations_live_next_to_the_entities() -> None:
    assert migration_locations([GameRecord]) == [Path(__file__).parent.parent / "data" / "migrations"]


def test_migrate_runs_every_pending_script_once(database: Database, tmp_path: Path) -> None:
    write(tmp_path, "V1__create_games.sql", "CREATE TABLE games (id INTEGER PRIMARY KEY);")
    write(
        tmp_path, "V2__create_moves.sql", "CREATE TABLE moves (id INTEGER PRIMARY KEY);\nCREATE INDEX m ON moves (id);"
    )
    migrations = SchemaMigrations(database, migrations_in([tmp_path]))

    first = migrations.migrate()
    second = migrations.migrate()

    assert [migration.label for migration in first.applied] == ["1", "2"]
    assert (first.baselined, second.applied) == ((), ())
    assert tables_of(database) == {"games", "moves", HISTORY_TABLE}


def test_a_later_migration_runs_after_the_earlier_ones_ran(database: Database, tmp_path: Path) -> None:
    write(tmp_path, "V1__create_games.sql", "CREATE TABLE games (id INTEGER PRIMARY KEY);")
    SchemaMigrations(database, migrations_in([tmp_path])).migrate()
    write(tmp_path, "V2__add_a_status.sql", "ALTER TABLE games ADD COLUMN status VARCHAR(16);")

    migrations = SchemaMigrations(database, migrations_in([tmp_path]))

    assert [migration.label for migration in migrations.pending()] == ["2"]
    migrations.migrate()
    with database.session() as session:
        session.execute(text("INSERT INTO games (id, status) VALUES (1, 'waiting')"))


def test_a_script_that_changed_after_it_ran_stops_the_next_run(database: Database, tmp_path: Path) -> None:
    script = write(tmp_path, "V1__create_games.sql", "CREATE TABLE games (id INTEGER PRIMARY KEY);")
    SchemaMigrations(database, migrations_in([tmp_path])).migrate()
    script.write_text("CREATE TABLE games (id INTEGER PRIMARY KEY, status TEXT);", encoding="utf-8")

    with pytest.raises(InvalidMigrationError, match="changed after it ran"):
        SchemaMigrations(database, migrations_in([tmp_path])).migrate()


def test_a_line_end_of_another_checkout_changes_nothing(database: Database, tmp_path: Path) -> None:
    script = write(tmp_path, "V1__create_games.sql", "CREATE TABLE games (\n  id INTEGER PRIMARY KEY\n);\n")
    SchemaMigrations(database, migrations_in([tmp_path])).migrate()
    script.write_bytes(script.read_bytes().replace(b"\n", b"\r\n"))

    assert SchemaMigrations(database, migrations_in([tmp_path])).pending() == []


def test_a_version_the_database_ran_that_no_script_has_stops_the_run(database: Database, tmp_path: Path) -> None:
    write(tmp_path / "old", "V1__create_games.sql", "CREATE TABLE games (id INTEGER PRIMARY KEY);")
    SchemaMigrations(database, migrations_in([tmp_path / "old"])).migrate()

    with pytest.raises(InvalidMigrationError, match="which no migrations directory holds"):
        SchemaMigrations(database, []).pending()


def test_a_failing_script_leaves_no_trace_and_runs_again_once_fixed(database: Database, tmp_path: Path) -> None:
    script = write(tmp_path, "V1__create_games.sql", "CREATE TABLE games (id INTEGER PRIMARY KEY);\nCREATE TABLE (;")

    with pytest.raises(OperationalError):
        SchemaMigrations(database, migrations_in([tmp_path])).migrate()

    assert tables_of(database) == {HISTORY_TABLE}, "the first statement was rolled back with the second"
    script.write_text("CREATE TABLE games (id INTEGER PRIMARY KEY);", encoding="utf-8")
    applied = SchemaMigrations(database, migrations_in([tmp_path])).migrate().applied
    assert [migration.label for migration in applied] == ["1"]


def test_a_semicolon_in_a_string_a_comment_or_a_trigger_does_not_end_a_statement(
    database: Database, tmp_path: Path
) -> None:
    write(
        tmp_path,
        "V1__create_games.sql",
        """-- games; and their moves
CREATE TABLE games (id INTEGER PRIMARY KEY, name TEXT NOT NULL DEFAULT 'a;b'); CREATE TABLE moves (game_id INTEGER);
CREATE TRIGGER first_move AFTER INSERT ON games BEGIN
    INSERT INTO moves (game_id) VALUES (new.id);
END;
INSERT INTO games (id) VALUES (1)
/* no semicolon after the last statement */""",
    )

    SchemaMigrations(database, migrations_in([tmp_path])).migrate()

    with database.session() as session:
        assert session.execute(text("SELECT name FROM games")).scalar_one() == "a;b"
        assert session.execute(text("SELECT game_id FROM moves")).scalar_one() == 1


def test_without_migrations_only_the_history_table_is_made(database: Database) -> None:
    assert SchemaMigrations(database, []).migrate() == MigrateResult(baselined=(), applied=())
    assert tables_of(database) == {HISTORY_TABLE}
