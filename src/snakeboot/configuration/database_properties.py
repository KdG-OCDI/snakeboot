import re
from typing import Any, Final

from pydantic import SecretStr, field_validator, model_validator

from snakeboot.configuration.configuration_properties import configuration_properties
from snakeboot.configuration.section import Section

SERVER_KEYS: Final = ("host", "port", "name", "user", "password")
"""The keys of a database server; a database in a file has `file` instead."""

MIGRATION_VERSION: Final = re.compile(r"\d+(?:\.\d+)*")
"""`1`, or `2.1` for `V2_1__...sql`: the version of a migration as the history of the migrations writes it."""


@configuration_properties("database")
class DatabaseProperties(Section):
    """The section `[database]`: the database of the service, like Spring Boot's `spring.datasource.*`.

    A PostgreSQL server, or one SQLite file, for a service that runs on one machine (a demo, a small tool):

        [database]                      # PostgreSQL; the password comes from DATABASE__PASSWORD
        host = "db"
        port = 5432
        name = "tictactoe"
        user = "tictactoe"

        [database]                      # SQLite
        file = "hexademo.sqlite3"       # relative to the directory the service starts in

    A table holds the keys of one kind and leaves out the other's, which read as None; both kinds at once stop the
    start. Since a profile and the environment change keys and cannot remove one, the kind is the same in every
    profile. snakeboot hands the database to the persistence framework when the table is there; an application
    without the table has no database.

    The optional `baseline_version`, like Flyway's `spring.flyway.baseline-on-migrate` with `baseline-version`, is
    for a database whose schema was made before its migrations, by another tool or by hand: when `migrate` finds
    tables there but no history of migrations, it first records every migration up to that version as run, without
    running it. `baseline_version = 1`, or `"2.1"` for `V2_1__...sql`; without the key, None: no baseline.
    """

    host: str | None
    port: int | None
    name: str | None
    user: str | None
    password: SecretStr | None
    file: str | None
    baseline_version: str | None

    @model_validator(mode="before")
    @classmethod
    def _a_server_or_a_file(cls, table: Any) -> Any:
        if not isinstance(table, dict):
            return table
        # A key given as None is no key: code that builds the section itself passes every field, as for any section.
        given = {key for key, value in table.items() if value is not None}
        if "file" not in given:
            return {**table, "file": None}
        if server_keys := [key for key in SERVER_KEYS if key in given]:
            raise ValueError(f"[database] is a server or a file, not both: leave out {', '.join(server_keys)}.")
        return {**dict.fromkeys(SERVER_KEYS), **table}

    @model_validator(mode="before")
    @classmethod
    def _without_a_baseline(cls, table: Any) -> Any:
        # A profile and the environment change keys and cannot write None: a missing key reads as None.
        return {"baseline_version": None, **table} if isinstance(table, dict) else table

    @field_validator("baseline_version", mode="before")
    @classmethod
    def _a_version_of_a_migration(cls, version: Any) -> Any:
        # TOML writes `1` as a number, the environment as text; the history of the migrations keeps it as text.
        written = str(version) if isinstance(version, int) else version
        if written is not None and (not isinstance(written, str) or MIGRATION_VERSION.fullmatch(written) is None):
            raise ValueError(
                '[database] baseline_version is the version of a migration: 1 for V1__...sql, "2.1" for V2_1__...sql; '
                f"not {version!r}."
            )
        return written
