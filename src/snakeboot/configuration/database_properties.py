from pydantic import SecretStr

from snakeboot.configuration.configuration_properties import configuration_properties
from snakeboot.configuration.section import Section


@configuration_properties("database")
class DatabaseProperties(Section):
    """The section `[database]`: the PostgreSQL database of the service, like Spring Boot's `spring.datasource.*`.

    snakeboot hands it to the persistence framework of the application when the table is there; an application
    without the table has no database.
    """

    host: str
    port: int
    name: str
    user: str
    password: SecretStr
