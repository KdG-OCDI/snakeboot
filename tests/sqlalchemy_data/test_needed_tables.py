"""A table of snakeboot's own is part of the schema only once a method needs it, as a starter's table in Spring Boot.

The migrations of an application without `@application_module_listener` or `@scheduler_lock` methods need no table of
snakeboot's, the database of its tests checks for none, and `make_migration` writes none: a Spring Boot application
has no `event_publication` or `shedlock` table before it has Spring Modulith's or ShedLock's starter either.
"""

from collections.abc import Callable
from pathlib import Path
from typing import override

from sqlalchemy import inspect

from snakeboot.component_scan import ComponentScan, MarkedMethod
from snakeboot.event_publication import EventPublicationRecord
from snakeboot.lifecycle import ApplicationComponents
from snakeboot.scheduler_lock import SchedulerLockRecord
from snakeboot.sqlalchemy_data.in_memory_sqlite import in_memory_database
from snakeboot.sqlalchemy_data.schema_entities import entities_of_the_schema
from snakeboot.sqlalchemy_data.schema_migrations import HISTORY_TABLE, SchemaMigrations, migrations_in
from snakeboot.sqlalchemy_data.sqlalchemy_data_injectable import migration_generator
from tests.sqlalchemy_data.needed_tables.plain import NoteRecord

SNAKEBOOTS_TABLES = (
    "snakeboot.event_publication.event_publication_record",
    "snakeboot.scheduler_lock.scheduler_lock_record",
)


class ScannedModule(ApplicationComponents):
    """Stands in for the application context: one module of `needed_tables`, with snakeboot's own tables mapped, as
    every application with `[database]` maps them."""

    def __init__(self, module: str) -> None:
        self._scan = ComponentScan(
            (f"tests.sqlalchemy_data.needed_tables.{module}",), auto_configuration=SNAKEBOOTS_TABLES
        )

    @override
    def classes_marked(self, marker: str) -> list[type]:
        return self._scan.classes_marked(marker)

    @override
    def methods_marked[M](self, marker: str, mapping_type: type[M]) -> list[MarkedMethod[M]]:
        return self._scan.methods_marked(marker, mapping_type)

    @override
    def get[T](self, component_type: Callable[..., T]) -> T:
        raise LookupError(repr(component_type))


def test_listeners_without_the_outbox_and_scheduled_methods_without_a_lock_need_no_table_of_snakeboots() -> None:
    assert entities_of_the_schema(ScannedModule("plain")) == [NoteRecord]


def test_an_application_module_listener_needs_the_table_of_the_event_publication_registry() -> None:
    assert entities_of_the_schema(ScannedModule("outboxed")) == [EventPublicationRecord]


def test_a_scheduler_lock_needs_the_table_of_the_scheduler_locks() -> None:
    assert entities_of_the_schema(ScannedModule("locked")) == [SchedulerLockRecord]


def test_the_database_of_a_test_builds_and_checks_only_the_tables_the_application_needs(tmp_path: Path) -> None:
    (tmp_path / "V1__create_plain_note.sql").write_bytes(
        b"CREATE TABLE plain_note (note_id INTEGER NOT NULL, text VARCHAR NOT NULL, PRIMARY KEY (note_id));\n"
    )

    database = in_memory_database(entities_of_the_schema(ScannedModule("plain")), migrations=migrations_in([tmp_path]))

    assert sorted(inspect(database.engine).get_table_names()) == ["plain_note", HISTORY_TABLE]
    database.close()


def test_make_migration_writes_a_table_of_snakeboots_only_once_a_method_needs_it() -> None:
    for module, written, left_out in [
        ("plain", "CREATE TABLE plain_note", "snakeboot_"),
        ("outboxed", "CREATE TABLE snakeboot_event_publication", "snakeboot_scheduler_lock"),
        ("locked", "CREATE TABLE snakeboot_scheduler_lock", "snakeboot_event_publication"),
    ]:
        database = in_memory_database()
        components = ScannedModule(module)

        changes = migration_generator(database, components, SchemaMigrations(database, [])).changes()

        assert written in changes, module
        assert left_out not in changes, module
        database.close()
