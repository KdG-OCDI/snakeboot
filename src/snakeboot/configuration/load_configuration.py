from collections.abc import Sequence

from snakeboot.configuration.configuration import Configuration
from snakeboot.configuration.configuration_sources import ConfigurationSources, sections_by_prefix
from snakeboot.configuration.section import Section


def load_configuration(*sections: type[Section], package: str) -> Configuration:
    """Loads `sections` from the files in `package` and the environment, like Spring Boot's `application.yml`.

    Three sources; a later one overrides an earlier one key by key, so nested tables are merged:

        application.toml              every value the application runs with
        application-<profile>.toml    only when SNAKEBOOT_PROFILE names a profile
        environment variables         SECTION__KEY__SUBKEY, for example CHATBOT__LLM__MODEL

    Nothing else is read: no `.env` file, no default in code, no command line. The files are package
    data, so a source checkout and an installed wheel find them alike. Everything fails here, at
    start-up: InvalidConfigurationPropertiesError for a broken model, ConfigurationFileNotFoundError
    for a missing file, pydantic's ValidationError for a missing, unknown or invalid value.

    This takes both steps at once. A Django application lets `snakeboot.django_application` take them: the
    sections of the container are then found in its modules instead of listed.
    """
    configuration = begin_configuration(*sections, package=package)
    configuration.complete()
    return configuration


def begin_configuration(
    *sections: type[Section], optional: Sequence[type[Section]] = (), package: str
) -> Configuration:
    """Reads the sections known before the container is built; `Configuration.complete` reads the others.

    `optional` sections are read when the files or the environment have their table, and are absent otherwise.
    Every other table waits for `complete`, which refuses the tables that no section claims.
    """
    return Configuration(
        ConfigurationSources.of(package),
        required=sections_by_prefix(sections),
        optional=sections_by_prefix(optional),
    )
