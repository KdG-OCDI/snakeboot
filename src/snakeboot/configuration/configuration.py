from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Annotated, Final

from wireup import Inject, injectable

from snakeboot.configuration.configuration_errors import InvalidConfigurationPropertiesError
from snakeboot.configuration.configuration_sources import ConfigurationSources, sections_by_prefix
from snakeboot.configuration.section import Section

CONFIGURATION_KEY: Final = "CONFIGURATION"
"""The key of the container's config that holds the `Configuration`: in a Django application, the setting of that name.

The provider of every section reads it there, so the container needs no list of sections.
"""


class Configuration:
    """What was read: the active profile and one validated, immutable object per section.

    A container brings sections of its own, and they are known only once its modules are imported. So the
    configuration is read in two steps. `begin_configuration` reads the sections known beforehand and leaves every
    other table for later; `complete` reads everything again, together with the sections of the container, and
    then refuses a table that no section claims. `load_configuration` does both steps at once.
    """

    def __init__(
        self,
        sources: ConfigurationSources,
        required: Mapping[str, type[Section]],
        optional: Mapping[str, type[Section]],
    ) -> None:
        self._sources = sources
        self._required = dict(required)
        self._optional = dict(optional)
        self._loaded = sources.read(self._required, self._optional, unknown_tables="ignore")
        self._complete = False

    @property
    def profile(self) -> str | None:
        """The active profile, or None."""
        return self._sources.profile

    @property
    def sections(self) -> Mapping[type[Section], Section]:
        """Every section read so far, by its class."""
        return MappingProxyType(self._loaded)

    def complete(self, *sections: type[Section]) -> None:
        """Reads the configuration again with `sections` added, and refuses a table that no section claims.

        This is the second step, taken once: `snakeboot.django_application` takes it when Django starts, with the
        sections declared in the modules of the container.
        """
        if self._complete:
            raise InvalidConfigurationPropertiesError("The configuration is complete already: it is read once.")
        known = {*self._required.values(), *self._optional.values()}
        required = sections_by_prefix([*self._required.values(), *(s for s in sections if s not in known)])
        optional = {prefix: section for prefix, section in self._optional.items() if prefix not in required}
        self._loaded = self._sources.read(required, optional, unknown_tables="forbid")
        self._complete = True

    def get[S: Section](self, section: type[S]) -> S:
        """Returns the object read for `section`."""
        loaded = self._loaded.get(section)
        if isinstance(loaded, section):
            return loaded
        raise LookupError(self._why_missing(section))

    def _why_missing(self, section: type[Section]) -> str:
        if section in self._optional.values():
            return f"{section.__name__} has no table in the files or the environment, so it was not read."
        if not self._complete:
            return (
                f"{section.__name__} is not read yet: the sections of the container are read when it is built "
                "(Configuration.complete; snakeboot.django_application does it when Django starts)."
            )
        return (
            f"{section.__name__} is not a section of this configuration: no module of the container declares it, "
            "and load_configuration was not given it."
        )


def provider_of[S: Section](section: type[S], prefix: str) -> Callable[..., S]:
    """Returns the wireup provider of `section`: it hands out the object the configuration read.

    The provider finds the configuration in the container's config, under `CONFIGURATION_KEY`.
    """

    def provide(configuration: Configuration) -> S:
        return configuration.get(section)

    provide.__name__ = provide.__qualname__ = f"provide_{prefix}_properties"
    provide.__annotations__ = {
        "configuration": Annotated[Configuration, Inject(config=CONFIGURATION_KEY)],
        "return": section,
    }
    return injectable(provide)
