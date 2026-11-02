"""Technical library: typed configuration from application.toml, one profile and the environment.

    @configuration_properties("chatbot")         # @ConfigurationProperties(prefix = "chatbot")
    class ChatbotProperties(Section):
        model: str                               # no default: the value is in application.toml

    # in settings.py, like @EnableConfigurationProperties({DjangoProperties.class, ChatbotProperties.class}):
    CONFIGURATION = load_configuration(DjangoProperties, ChatbotProperties, package="myservice")
    SECRET_KEY = CONFIGURATION.get(DjangoProperties).secret_key.get_secret_value()
    WIREUP = WireupSettings(injectables=[*scan.module_names(), *CONFIGURATION.injectables()])

The values come from `application.toml` in the package, then `application-<profile>.toml` when
SNAKEBOOT_PROFILE is set, then environment variables such as CHATBOT__MODEL; nothing else.
`DjangoProperties`, `DatabaseProperties` and `CacheProperties` are the sections Django itself needs.
"""

from snakeboot.configuration.cache_properties import CacheProperties
from snakeboot.configuration.configuration import Configuration
from snakeboot.configuration.configuration_errors import (
    ConfigurationFileNotFoundError,
    InvalidConfigurationPropertiesError,
)
from snakeboot.configuration.configuration_properties import configuration_properties
from snakeboot.configuration.database_properties import DatabaseProperties
from snakeboot.configuration.django_properties import DjangoProperties
from snakeboot.configuration.load_configuration import BASE_FILE, PROFILE_VARIABLE, load_configuration
from snakeboot.configuration.section import Section

__all__ = [
    "BASE_FILE",
    "PROFILE_VARIABLE",
    "CacheProperties",
    "Configuration",
    "ConfigurationFileNotFoundError",
    "DatabaseProperties",
    "DjangoProperties",
    "InvalidConfigurationPropertiesError",
    "Section",
    "configuration_properties",
    "load_configuration",
]
