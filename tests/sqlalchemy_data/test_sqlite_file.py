"""`[database] file` keeps the database in one SQLite file, shared by every thread of the service."""

import threading
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from snakeboot.configuration import DatabaseProperties
from snakeboot.sqlalchemy_data import Database
from snakeboot.sqlalchemy_data.schema_migrations import HISTORY_TABLE, SchemaMigrations, migrations_in

WRITERS = 4
WRITES = 25


def file_database(tmp_path: Path) -> Database:
    return Database.of(DatabaseProperties.model_validate({"file": str(tmp_path / "service.sqlite3")}))


def test_a_table_with_a_file_is_a_database_in_that_file() -> None:
    properties = DatabaseProperties.model_validate({"file": "hexademo.sqlite3"})

    assert (properties.file, properties.host, properties.password) == ("hexademo.sqlite3", None, None)


def test_a_table_with_a_server_still_needs_every_key_of_the_server() -> None:
    with pytest.raises(ValidationError, match="name"):
        DatabaseProperties.model_validate({"host": "db", "port": 5432, "user": "u", "password": "p"})


def test_a_table_with_a_server_and_a_file_stops_the_start() -> None:
    with pytest.raises(ValidationError, match="a server or a file, not both: leave out host"):
        DatabaseProperties.model_validate({"file": "x.sqlite3", "host": "db"})


def test_a_key_given_as_none_is_no_key_of_the_other_kind() -> None:
    server = DatabaseProperties(
        host="db", port=5432, name="shop", user="shop", password=None, file=None, baseline_version=None
    )
    in_a_file = DatabaseProperties(
        host=None, port=None, name=None, user=None, password=None, file="shop.sqlite3", baseline_version=None
    )

    assert (server.host, server.file, in_a_file.file, in_a_file.host) == ("db", None, "shop.sqlite3", None)


def test_what_one_transaction_saved_the_next_reads_from_the_file(tmp_path: Path) -> None:
    database = file_database(tmp_path)
    with database.transaction() as session:
        session.execute(text("CREATE TABLE seats (id INTEGER PRIMARY KEY)"))
        session.execute(text("INSERT INTO seats (id) VALUES (1)"))
    database.close()

    reopened = file_database(tmp_path)
    with reopened.session() as session:
        assert session.execute(text("SELECT COUNT(*) FROM seats")).scalar_one() == 1
    reopened.close()


def test_threads_that_write_at_once_wait_for_each_other_instead_of_failing(tmp_path: Path) -> None:
    database = file_database(tmp_path)
    with database.transaction() as session:
        session.execute(text("CREATE TABLE seats (id INTEGER PRIMARY KEY, taken INTEGER NOT NULL)"))
        session.execute(text("INSERT INTO seats (id, taken) VALUES (1, 0)"))
    failures: list[BaseException] = []

    def take_seats() -> None:
        try:
            for _ in range(WRITES):
                with database.transaction() as session:
                    taken = session.execute(text("SELECT taken FROM seats WHERE id = 1")).scalar_one()
                    session.execute(text("UPDATE seats SET taken = :taken WHERE id = 1"), {"taken": taken + 1})
        except BaseException as error:  # noqa: BLE001  # reason: the test reports what a writer met
            failures.append(error)

    writers = [threading.Thread(target=take_seats) for _ in range(WRITERS)]
    for writer in writers:
        writer.start()
    for writer in writers:
        writer.join()

    with database.session() as session:
        taken = session.execute(text("SELECT taken FROM seats WHERE id = 1")).scalar_one()
    database.close()
    assert (failures, taken) == ([], WRITERS * WRITES)


def test_the_migrations_run_on_a_file(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "V1__create_seats.sql").write_text("CREATE TABLE seats (id INTEGER PRIMARY KEY);\n", encoding="utf-8")
    database = file_database(tmp_path)

    applied = SchemaMigrations(database, migrations_in([migrations])).migrate().applied

    assert [migration.label for migration in applied] == ["1"]
    assert SchemaMigrations(database, migrations_in([migrations])).pending() == []
    database.close()


def test_a_failing_migration_leaves_no_half_of_its_script_in_the_file(tmp_path: Path) -> None:
    """Python's sqlite3 commits before `executescript`; the migration's own transaction must hold every statement."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "V1__create_seats.sql").write_text(
        "CREATE TABLE seats (id INTEGER PRIMARY KEY);\nCREATE TABLE (;\n", encoding="utf-8"
    )
    database = file_database(tmp_path)

    with pytest.raises(OperationalError):
        SchemaMigrations(database, migrations_in([migrations])).migrate()

    assert inspect(database.engine).get_table_names() == [HISTORY_TABLE]
    database.close()
