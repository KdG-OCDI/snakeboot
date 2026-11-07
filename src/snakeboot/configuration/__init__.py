"""Technical library: typed configuration from application.toml, one profile and the environment.

    @configuration_properties("chatbot")         # @ConfigurationProperties(prefix = "chatbot")
    class ChatbotProperties(Section):
        model: str                               # no default: the value is in application.toml

The values come from `application.toml` in the package, then `application-<profile>.toml` when
SNAKEBOOT_PROFILE is set, then environment variables such as CHATBOT__MODEL; nothing else.

A section is a component of the module that declares it, so it enters the container with that module. In a Django
application, `snakeboot.django_application` reads every section, Django's own included; without Django,
`load_configuration(ChatbotProperties, package="myservice")` reads the sections it is given.
`DjangoProperties`, `DatabaseProperties` and `CacheProperties` are the sections Django itself needs;
`OAuth2Properties` names the authorization server whose tokens `snakeboot.oauth2` accepts; `SchedulingProperties`
turns `@scheduled` methods off in a process; `RabbitProperties` names the broker of `snakeboot.rabbitmq`.
"""

from snakeboot.configuration.cache_properties import CacheProperties
from snakeboot.configuration.configuration import CONFIGURATION_KEY, Configuration
from snakeboot.configuration.configuration_errors import (
    ConfigurationFileNotFoundError,
    InvalidConfigurationPropertiesError,
)
from snakeboot.configuration.configuration_properties import configuration_properties
from snakeboot.configuration.configuration_sources import BASE_FILE, PROFILE_VARIABLE
from snakeboot.configuration.database_properties import DatabaseProperties
from snakeboot.configuration.django_properties import DjangoProperties
from snakeboot.configuration.load_configuration import begin_configuration, load_configuration
from snakeboot.configuration.oauth2_properties import OAuth2Properties
from snakeboot.configuration.rabbitmq_properties import RabbitListenerProperties, RabbitProperties
from snakeboot.configuration.scheduling_properties import SchedulingProperties
from snakeboot.configuration.section import Section
from snakeboot.configuration.section_prefix import sections_declared_in

__all__ = [
    "BASE_FILE",
    "CONFIGURATION_KEY",
    "PROFILE_VARIABLE",
    "CacheProperties",
    "Configuration",
    "ConfigurationFileNotFoundError",
    "DatabaseProperties",
    "DjangoProperties",
    "InvalidConfigurationPropertiesError",
    "OAuth2Properties",
    "RabbitListenerProperties",
    "RabbitProperties",
    "SchedulingProperties",
    "Section",
    "begin_configuration",
    "configuration_properties",
    "load_configuration",
    "sections_declared_in",
]
