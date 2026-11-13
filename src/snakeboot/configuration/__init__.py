"""Technical library: typed configuration from application.toml, one profile and the environment.

    @configuration_properties("chatbot")         # @ConfigurationProperties(prefix = "chatbot")
    class ChatbotProperties(Section):
        model: str                               # no default: the value is in application.toml

The values come from `application.toml` in the package, then `application-<profile>.toml` when
SNAKEBOOT_PROFILE is set, then environment variables such as CHATBOT__MODEL; nothing else.

A section is a component of the module that declares it, so it enters the container with that module. When the
application starts (`snakeboot.boot`), snakeboot reads every section, its own included; outside an application,
`load_configuration(ChatbotProperties, package="myservice")` reads the sections it is given.
`ServerProperties`, `DatabaseProperties` and `CacheProperties` are what the framework underneath needs, in no
framework's terms; `OAuth2Properties` names the authorization server whose tokens `snakeboot.oauth2` accepts;
`SchedulingProperties` turns `@scheduled` methods off in a process; `RabbitProperties` names the broker of
`snakeboot.rabbitmq`; `CorsProperties` the origins whose pages may call the REST API; `LoggingProperties` writes log
lines as JSON; `EventsProperties` times the event publication registry.
"""

from snakeboot.configuration.cache_properties import CacheProperties
from snakeboot.configuration.configuration import CONFIGURATION_KEY, Configuration
from snakeboot.configuration.configuration_errors import (
    ConfigurationFileNotFoundError,
    InvalidConfigurationPropertiesError,
)
from snakeboot.configuration.configuration_properties import configuration_properties
from snakeboot.configuration.configuration_sources import BASE_FILE, PROFILE_VARIABLE
from snakeboot.configuration.cors_properties import CorsProperties
from snakeboot.configuration.database_properties import DatabaseProperties
from snakeboot.configuration.events_properties import EventsProperties
from snakeboot.configuration.load_configuration import begin_configuration, load_configuration
from snakeboot.configuration.logging_properties import LoggingProperties
from snakeboot.configuration.oauth2_properties import OAuth2Properties
from snakeboot.configuration.rabbitmq_properties import (
    RabbitListenerProperties,
    RabbitListenerRetryProperties,
    RabbitProperties,
)
from snakeboot.configuration.scheduling_properties import SchedulingProperties
from snakeboot.configuration.section import Section
from snakeboot.configuration.section_prefix import sections_declared_in
from snakeboot.configuration.server_properties import ServerProperties

__all__ = [
    "BASE_FILE",
    "CONFIGURATION_KEY",
    "PROFILE_VARIABLE",
    "CacheProperties",
    "Configuration",
    "ConfigurationFileNotFoundError",
    "CorsProperties",
    "DatabaseProperties",
    "EventsProperties",
    "InvalidConfigurationPropertiesError",
    "LoggingProperties",
    "OAuth2Properties",
    "RabbitListenerProperties",
    "RabbitListenerRetryProperties",
    "RabbitProperties",
    "SchedulingProperties",
    "Section",
    "ServerProperties",
    "begin_configuration",
    "configuration_properties",
    "load_configuration",
    "sections_declared_in",
]
