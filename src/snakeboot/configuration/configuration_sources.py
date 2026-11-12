import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from importlib.resources import files
from importlib.resources.abc import Traversable
from typing import Any, Final, Literal, override

from pydantic import create_model
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict, TomlConfigSettingsSource

from snakeboot.configuration.configuration_errors import (
    ConfigurationFileNotFoundError,
    InvalidConfigurationPropertiesError,
)
from snakeboot.configuration.properties_rules import refuse_loose_models
from snakeboot.configuration.section import Section
from snakeboot.configuration.section_prefix import prefix_of

PROFILE_VARIABLE: Final = "SNAKEBOOT_PROFILE"
"""The environment variable that activates a profile, like `SPRING_PROFILES_ACTIVE` (one profile at most)."""

BASE_FILE: Final = "application.toml"
_PROFILE_NAME: Final = re.compile(r"[a-z][a-z0-9-]*")

type UnknownTables = Literal["ignore", "forbid"]


@dataclass(frozen=True, slots=True)
class ConfigurationSources:
    """Where the values come from: application.toml in `package`, the file of the active profile and the environment.

    A test may add `properties`, which override every other source, like `@SpringBootTest(properties = ...)`. The
    profile and the files are fixed when the sources are found, so reading twice reads the same files.
    """

    package: str
    profile: str | None
    files: tuple[Traversable, ...]
    properties: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def of(
        cls, package: str, *, profile: str | None = None, properties: Mapping[str, object] | None = None
    ) -> "ConfigurationSources":
        """Finds the files of `package` and the active profile; a missing file stops the start.

        `profile` activates a profile, like `@ActiveProfiles`, whatever SNAKEBOOT_PROFILE says. `properties` name a
        key with its table, `{"scheduling.auto_startup": False}`, and win over the files and the environment.
        """
        active = _checked_profile(profile) if profile is not None else _active_profile()
        return cls(
            package=package,
            profile=active,
            files=_configuration_files(package, active),
            properties=_nested(properties or {}),
        )

    def read(
        self,
        required: Mapping[str, type[Section]],
        optional: Mapping[str, type[Section]],
        *,
        unknown_tables: UnknownTables,
    ) -> dict[type[Section], Section]:
        """Reads every required section, and every optional one whose table the files or the environment have.

        `unknown_tables="forbid"` refuses a table that no section claims; `"ignore"` leaves it for a later read.
        """
        loaded = _root_model(required, optional, self.files, unknown_tables=unknown_tables)(**self.properties)
        read = {section: getattr(loaded, prefix) for prefix, section in {**required, **optional}.items()}
        return {section: value for section, value in read.items() if value is not None}


def sections_by_prefix(sections: Iterable[type[Section]]) -> dict[str, type[Section]]:
    """Returns `sections` by prefix; two sections with one prefix, or a section breaking a rule, stop the start."""
    by_prefix: dict[str, type[Section]] = {}
    for section in dict.fromkeys(sections):
        prefix = prefix_of(section)
        if (earlier := by_prefix.get(prefix)) is not None:
            raise InvalidConfigurationPropertiesError(
                f"{earlier.__name__} and {section.__name__} both claim the section [{prefix}]."
            )
        refuse_loose_models(section)
        by_prefix[prefix] = section
    return by_prefix


def _active_profile() -> str | None:
    profile = os.environ.get(PROFILE_VARIABLE, "")
    if profile and not _PROFILE_NAME.fullmatch(profile):
        raise ConfigurationFileNotFoundError(
            f"{PROFILE_VARIABLE}={profile!r} cannot name a profile file: a profile is one lowercase name."
        )
    return profile or None


def _checked_profile(profile: str) -> str:
    if not _PROFILE_NAME.fullmatch(profile):
        raise ConfigurationFileNotFoundError(
            f"The profile {profile!r} cannot name a profile file: a profile is one lowercase name."
        )
    return profile


def _nested(properties: Mapping[str, object]) -> dict[str, Any]:
    """`{"greeting.sender.name": "ann"}` as the tables it names: `{"greeting": {"sender": {"name": "ann"}}}`."""
    nested: dict[str, Any] = {}
    for key, value in properties.items():
        *tables, name = key.split(".")
        table = nested
        for part in tables:
            table = table.setdefault(part, {})
            if not isinstance(table, dict):
                raise InvalidConfigurationPropertiesError(f"The property {key!r} names a key inside a value.")
        table[name] = value
    return nested


def _configuration_files(package: str, profile: str | None) -> tuple[Traversable, ...]:
    directory = files(package)
    base = directory.joinpath(BASE_FILE)
    if not base.is_file():
        raise ConfigurationFileNotFoundError(f"{package} has no {BASE_FILE}: it holds every value of the application.")
    if profile is None:
        return (base,)
    profile_file = directory.joinpath(f"application-{profile}.toml")
    if not profile_file.is_file():
        raise ConfigurationFileNotFoundError(
            f"{PROFILE_VARIABLE}={profile}, but {package} has no application-{profile}.toml."
        )
    return base, profile_file


def _root_model(
    required: Mapping[str, type[Section]],
    optional: Mapping[str, type[Section]],
    toml_files: tuple[Traversable, ...],
    *,
    unknown_tables: UnknownTables,
) -> type[BaseSettings]:
    class RootSettings(BaseSettings):
        model_config = SettingsConfigDict(env_prefix="", env_nested_delimiter="__", extra=unknown_tables, frozen=True)

        @classmethod
        @override
        def settings_customise_sources(  # reason: the signature is pydantic-settings' hook
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
        ) -> tuple[PydanticBaseSettingsSource, ...]:
            # A test's properties, the environment and the files: no .env file, no secrets directory. An earlier
            # source wins, key by key.
            return (
                init_settings,
                env_settings,
                TomlConfigSettingsSource(settings_cls, toml_file=list(toml_files), deep_merge=True),
            )

    fields: dict[str, Any] = {prefix: (section, ...) for prefix, section in required.items()}
    # An optional section is absent when no file and no variable has its table; the root model may say so.
    fields |= {prefix: (section | None, None) for prefix, section in optional.items()}
    root: type[BaseSettings] = create_model("Configuration", __base__=RootSettings, **fields)
    return root
