from typing import override

from sqlalchemy import text

from snakeboot.actuator import HealthIndicator
from snakeboot.sqlalchemy_data.database import Database


class DatabaseHealthIndicator(HealthIndicator, component=False):
    """Checks that the database answers, like Spring Boot's `DataSourceHealthIndicator`: it runs `SELECT 1`."""

    def __init__(self, database: Database) -> None:
        self._database = database

    @override
    def check(self) -> None:
        with self._database.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
