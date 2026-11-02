from pydantic import SecretStr

from snakeboot.configuration.configuration_properties import configuration_properties
from snakeboot.configuration.section import Section


@configuration_properties("database")
class DatabaseProperties(Section):
    """The section `[database]`: the PostgreSQL database of the service, like Spring Boot's `spring.datasource.*`.

    DATABASES = {"default": CONFIGURATION.get(DatabaseProperties).as_django_database()}
    """

    host: str
    port: int
    name: str
    user: str
    password: SecretStr

    def as_django_database(self) -> dict[str, str]:
        """The entry of Django's `DATABASES` setting."""
        return {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": self.host,
            "PORT": str(self.port),
            "NAME": self.name,
            "USER": self.user,
            "PASSWORD": self.password.get_secret_value(),
        }
