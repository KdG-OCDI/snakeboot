"""`migrate` and `make_migration`: the schema's commands of every application with a database.

python -m myapp migrate                          # runs the SQL migrations the database has not run
python -m myapp make_migration "add a winner"    # writes the SQL the entities need as the next migration
"""

import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import override

from snakeboot.command_line import CommandLineRunner
from snakeboot.sqlalchemy_data.migration_generator import MigrationGenerator
from snakeboot.sqlalchemy_data.schema_migrations import SchemaMigrations


class MigrateCommand(CommandLineRunner, command="migrate"):
    """Brings the database's schema up to date, like Flyway's migrate.

    Runs every SQL migration of the application's entities that the database has not run, in version order, each in
    a transaction of its own. A script that changed after it ran stops the command.
    """

    def __init__(self, migrations: SchemaMigrations) -> None:
        self._migrations = migrations

    @override
    def run(self, arguments: Namespace) -> None:
        applied = self._migrations.migrate()
        for migration in applied:
            sys.stdout.write(f"Applied {migration.path.name}\n")
        if not applied:
            sys.stdout.write("The schema is up to date.\n")


class MakeMigrationCommand(CommandLineRunner, command="make_migration"):
    """Writes the SQL that brings the database's schema to the entities, as the next migration.

    Compares the entities with the database, which must have run every migration, and writes the difference as plain
    SQL next to the entities: V<next>__<description>.sql. Read it, change it if needed, and commit it.
    """

    def __init__(self, generator: MigrationGenerator) -> None:
        self._generator = generator

    @classmethod
    @override
    def add_arguments(cls, parser: ArgumentParser) -> None:
        parser.add_argument("description", help="What the migration does, in words: 'add a winner'.")
        parser.add_argument("--into", type=Path, help="The migrations directory, when the entities live in several.")

    @override
    def run(self, arguments: Namespace) -> None:
        sql = self._generator.changes()
        if not sql:
            sys.stdout.write("The schema fits the entities: no migration written.\n")
            return
        path = self._generator.write(arguments.description, sql, arguments.into)
        sys.stdout.write(f"Wrote {path}\n")
