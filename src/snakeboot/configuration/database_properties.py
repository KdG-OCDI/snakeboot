from typing import Any, Final

from pydantic import SecretStr, model_validator

from snakeboot.configuration.configuration_properties import configuration_properties
from snakeboot.configuration.section import Section

SERVER_KEYS: Final = ("host", "port", "name", "user", "password")
"""The keys of a database server; a database in a file has `file` instead."""


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
    """

    host: str | None
    port: int | None
    name: str | None
    user: str | None
    password: SecretStr | None
    file: str | None

    @model_validator(mode="before")
    @classmethod
    def _a_server_or_a_file(cls, table: Any) -> Any:
        if not isinstance(table, dict) or "file" not in table:
            return {**table, "file": None} if isinstance(table, dict) else table
        if server_keys := [key for key in SERVER_KEYS if key in table]:
            raise ValueError(f"[database] is a server or a file, not both: leave out {', '.join(server_keys)}.")
        return {**dict.fromkeys(SERVER_KEYS), **table}
