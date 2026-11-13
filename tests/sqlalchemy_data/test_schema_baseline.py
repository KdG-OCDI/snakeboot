"""`[database] baseline_version`, like Flyway's baselineOnMigrate: a database whose schema was made before its
migrations records the migrations up to the baseline as run, without running them; a fresh database, or one with a
history of migrations, runs them as before."""

from argparse import Namespace
from collections.abc import Iterable, Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from snakeboot.configuration import DatabaseProperties
from snakeboot.sqlalchemy_data import Database
from snakeboot.sqlalchemy_data.entity_mapping import EntityMapping
from snakeboot.sqlalchemy_data.migration_commands import MigrateCommand
from snakeboot.sqlalchemy_data.schema_migrations import (
    BASELINE_CHECKSUM,
    HISTORY_TABLE,
    InvalidMigrationError,
    Migration,
    SchemaMigrations,
    migrations_in,
)
from snakeboot.sqlalchemy_data.sqlalchemy_data_injectable import schema_migrations
from tests.application.sample_service.games.game_record import GameRecord

OLD_TABLES = (
    "CREATE TABLE games (id INTEGER PRIMARY KEY, name VARCHAR(40) NOT NULL CHECK (name <> ''))",
    "CREATE INDEX games_name_idx ON games (name)",
)
"""The schema an earlier version of the application left, made by another tool: no history of migrations."""

V1 = "".join(f"{statement};\n" for statement in OLD_TABLES)
"""The migration that holds that schema, so that a fresh database gets it too."""

V2 = "ALTER TABLE games ADD COLUMN status VARCHAR(16);\n"


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    database = Database.of(DatabaseProperties.model_validate({"file": str(tmp_path / "service.sqlite3")}))
    yield database
    database.close()


@pytest.fixture
def scripts(tmp_path: Path) -> Path:
    return write(tmp_path / "migrations", V1__schema_before_snakeboot=V1, V2__add_a_status=V2)


def write(location: Path, **scripts: str) -> Path:
    location.mkdir(parents=True, exist_ok=True)
    for name, sql in scripts.items():
        (location / f"{name}.sql").write_text(sql, encoding="utf-8")
    return location


def made_before_the_migrations(database: Database) -> None:
    with database.transaction() as session:
        for statement in OLD_TABLES:
            session.execute(text(statement))
        session.execute(text("INSERT INTO games (id, name) VALUES (1, 'kept')"))


def labels(migrations: Iterable[Migration]) -> list[str]:
    return [migration.label for migration in migrations]


def history_of(database: Database) -> dict[str, str]:
    """The checksum the history keeps, by version."""
    with database.engine.connect() as connection:
        return dict(connection.execute(text(f"SELECT version, checksum FROM {HISTORY_TABLE}")).all())


def test_tables_without_a_history_record_the_baseline_and_run_only_the_later_migrations(
    database: Database, scripts: Path
) -> None:
    made_before_the_migrations(database)

    # Run, V1 would fail: its table is there.
    result = SchemaMigrations(database, migrations_in([scripts]), baseline_version="1").migrate()

    assert (labels(result.baselined), labels(result.applied)) == (["1"], ["2"])
    v2 = migrations_in([scripts])[1]
    assert history_of(database) == {"1": BASELINE_CHECKSUM, "2": v2.checksum}
    with database.session() as session:
        assert session.execute(text("SELECT name, status FROM games")).one() == ("kept", None)


def test_every_migration_up_to_and_including_the_baseline_is_recorded_without_running(
    database: Database, tmp_path: Path
) -> None:
    table, index = (f"{statement};\n" for statement in OLD_TABLES)
    scripts = write(tmp_path, V1__create_games=table, V1_1__index_the_names=index, V2__add_a_status=V2)
    made_before_the_migrations(database)

    result = SchemaMigrations(database, migrations_in([scripts]), baseline_version="1.1").migrate()

    assert (labels(result.baselined), labels(result.applied)) == (["1", "1.1"], ["2"])


def test_an_empty_database_runs_every_migration_whatever_the_baseline(database: Database, scripts: Path) -> None:
    result = SchemaMigrations(database, migrations_in([scripts]), baseline_version="1").migrate()

    assert (labels(result.baselined), labels(result.applied)) == ([], ["1", "2"])
    assert BASELINE_CHECKSUM not in history_of(database).values()


def test_a_database_with_a_history_is_never_baselined(database: Database, scripts: Path) -> None:
    v1, _ = migrations_in([scripts])
    SchemaMigrations(database, [v1]).migrate()

    result = SchemaMigrations(database, migrations_in([scripts]), baseline_version="2").migrate()

    assert (labels(result.baselined), labels(result.applied)) == ([], ["2"])


def test_without_a_baseline_tables_the_migrations_leave_alone_change_nothing(
    database: Database, tmp_path: Path
) -> None:
    with database.transaction() as session:
        session.execute(text("CREATE TABLE legacy (id INTEGER PRIMARY KEY)"))
    scripts = write(tmp_path, V1__create_moves="CREATE TABLE moves (id INTEGER PRIMARY KEY);\n")

    result = SchemaMigrations(database, migrations_in([scripts])).migrate()

    assert (labels(result.baselined), labels(result.applied)) == ([], ["1"])


def test_without_a_baseline_a_first_migration_that_fails_on_older_tables_names_baseline_version(
    database: Database, scripts: Path
) -> None:
    made_before_the_migrations(database)

    with pytest.raises(
        InvalidMigrationError,
        match=r"(?s)V1__schema_before_snakeboot\.sql failed on a database that already held tables, but no history "
        r"of migrations: table games already exists\n.*set \[database\] baseline_version",
    ):
        SchemaMigrations(database, migrations_in([scripts])).migrate()


def test_the_baseline_that_failure_asks_for_baselines_the_database_on_the_next_migrate(
    database: Database, scripts: Path
) -> None:
    made_before_the_migrations(database)
    with pytest.raises(InvalidMigrationError):
        SchemaMigrations(database, migrations_in([scripts])).migrate()  # leaves an empty history table

    result = SchemaMigrations(database, migrations_in([scripts]), baseline_version="1").migrate()

    assert (labels(result.baselined), labels(result.applied)) == (["1"], ["2"])


def test_a_baselined_script_may_still_change_as_the_database_never_ran_it(database: Database, scripts: Path) -> None:
    made_before_the_migrations(database)
    SchemaMigrations(database, migrations_in([scripts]), baseline_version="1").migrate()

    (scripts / "V1__schema_before_snakeboot.sql").write_text(f"-- corrected for a fresh database\n{V1}", "utf-8")

    assert SchemaMigrations(database, migrations_in([scripts]), baseline_version="1").pending() == []


@pytest.mark.parametrize(
    ("baseline_version", "versions"), [("3", "1, 2"), ("1.0", "1, 2")], ids=["too high", "written otherwise"]
)
def test_a_baseline_that_names_no_migration_stops_the_start(
    database: Database, scripts: Path, baseline_version: str, versions: str
) -> None:
    named = rf'baseline_version = "{baseline_version}" names no migration \(the versions are: {versions}\)'
    with pytest.raises(InvalidMigrationError, match=named):
        SchemaMigrations(database, migrations_in([scripts]), baseline_version=baseline_version)


def test_a_baseline_without_migrations_stops_the_start(database: Database) -> None:
    with pytest.raises(InvalidMigrationError, match=r"names no migration \(the versions are: none\)"):
        SchemaMigrations(database, [], baseline_version="1")


def test_without_the_key_there_is_no_baseline() -> None:
    in_a_file = DatabaseProperties.model_validate({"file": "x.sqlite3"})
    on_a_server = DatabaseProperties.model_validate(
        {"host": "db", "port": 5432, "name": "n", "user": "u", "password": "p"}
    )

    assert (in_a_file.baseline_version, on_a_server.baseline_version) == (None, None)


@pytest.mark.parametrize(("written", "version"), [(1, "1"), ("1", "1"), ("2.1", "2.1")])
def test_the_baseline_is_a_number_or_a_version_in_text(written: object, version: str) -> None:
    properties = DatabaseProperties.model_validate({"file": "x.sqlite3", "baseline_version": written})

    assert properties.baseline_version == version


@pytest.mark.parametrize("written", ["V1", "2_1", "", 2.1, True])
def test_a_baseline_that_is_no_version_stops_the_start(written: object) -> None:
    with pytest.raises(ValidationError, match="baseline_version is the version of a migration"):
        DatabaseProperties.model_validate({"file": "x.sqlite3", "baseline_version": written})


def test_migrate_baselines_the_database_of_the_configuration_and_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    properties = DatabaseProperties.model_validate({"file": str(tmp_path / "service.sqlite3"), "baseline_version": 1})
    database = Database.of(properties)
    with database.transaction() as session:
        session.execute(text("CREATE TABLE sample_game (game_id UUID NOT NULL PRIMARY KEY)"))
    command = MigrateCommand(schema_migrations(database, EntityMapping.of([GameRecord]), properties))

    command.run(Namespace())

    database.close()
    assert capsys.readouterr().out == (
        "Baselined V1__create_sample_game.sql: recorded as run, without running it\n"
        "Applied V2__create_the_tables_of_snakeboot.sql\n"
    )
