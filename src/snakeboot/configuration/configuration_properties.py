import sys
from collections.abc import Callable

from snakeboot.configuration.configuration import provider_of
from snakeboot.configuration.configuration_errors import InvalidConfigurationPropertiesError
from snakeboot.configuration.section import Section
from snakeboot.configuration.section_prefix import PREFIX, PREFIX_ATTRIBUTE


def configuration_properties[M: type[Section]](prefix: str) -> Callable[[M], M]:
    """Binds a `Section` to the table `[prefix]`, like Spring's `@ConfigurationProperties(prefix = ...)`.

    The model receives the table `[prefix]` of `application.toml`, merged with the active profile and the
    environment variables `PREFIX__FIELD__SUBFIELD` (`CHATBOT__LLM__MODEL` sets `chatbot.llm.model`). The
    prefix is one lowercase name with single underscores: a double underscore separates the levels of an
    environment variable.

    The section is a component of the module that declares it: the decorator puts a wireup provider next to it,
    `provide_<prefix>_properties`, which hands out the object the configuration read. So when the component scan
    puts that module in the container, the section comes along, and an adapter asks for it by type. Give it no
    `@component`, as a Spring Boot record with `@ConfigurationProperties` has no `@Component`: wireup would build
    the model from its fields, not from the files.
    """
    if not PREFIX.fullmatch(prefix):
        raise InvalidConfigurationPropertiesError(
            f"A configuration prefix is one lowercase name with single underscores, got {prefix!r}."
        )

    def declare(model: M) -> M:
        if not _is_section(model):
            raise InvalidConfigurationPropertiesError(
                f"@configuration_properties marks a class that extends Section, not {model!r}."
            )
        setattr(model, PREFIX_ATTRIBUTE, prefix)
        _put_provider_next_to(model, prefix)
        return model

    return declare


def _put_provider_next_to(section: type[Section], prefix: str) -> None:
    # wireup registers every @injectable function among the members of a module it scans.
    module = sys.modules.get(section.__module__)
    if module is not None:
        provider = provider_of(section, prefix)
        setattr(module, provider.__name__, provider)


def _is_section(candidate: object) -> bool:
    return isinstance(candidate, type) and issubclass(candidate, Section)
