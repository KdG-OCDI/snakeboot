import os
import re
from collections.abc import Sequence
from importlib.resources import files
from importlib.resources.abc import Traversable
from types import MappingProxyType
from typing import Any, Final, override

from pydantic import BaseModel, create_model
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict, TomlConfigSettingsSource

from snakeboot.configuration.configuration import Configuration
from snakeboot.configuration.configuration_errors import (
    ConfigurationFileNotFoundError,
    InvalidConfigurationPropertiesError,
)
from snakeboot.configuration.configuration_properties import prefix_of
from snakeboot.configuration.properties_rules import refuse_loose_models

PROFILE_VARIABLE: Final = "SNAKEBOOT_PROFILE"
"""The environment variable that activates a profile, like `SPRING_PROFILES_ACTIVE` (one profile at most)."""

BASE_FILE: Final = "application.toml"
_PROFILE_NAME: Final = re.compile(r"[a-z][a-z0-9-]*")


def load_configuration(*sections: type[BaseModel], package: str) -> Configuration:
    """Loads `sections` from the files in `package` and the environment, like Spring Boot's `application.yml`.

    Three sources; a later one overrides an earlier one key by key, so nested tables are merged:

        application.toml              every value the application runs with
        application-<profile>.toml    only when SNAKEBOOT_PROFILE names a profile
        environment variables         SECTION__KEY__SUBKEY, for example CHATBOT__LLM__MODEL

    Nothing else is read: no `.env` file, no default in code, no command line. The files are package
    data, so a source checkout and an installed wheel find them alike. Everything fails here, at
    start-up: InvalidConfigurationPropertiesError for a broken model, ConfigurationFileNotFoundError
    for a missing file, pydantic's ValidationError for a missing, unknown or invalid value.
    """
    sections_by_prefix = _sections_by_prefix(sections)
    profile = _active_profile()
    root_model = _root_model(sections_by_prefix, _configuration_files(package, profile))
    loaded = root_model()
    return Configuration(
        profile=profile,
        sections=MappingProxyType({section: getattr(loaded, prefix) for prefix, section in sections_by_prefix.items()}),
    )


def _sections_by_prefix(sections: Sequence[type[BaseModel]]) -> dict[str, type[BaseModel]]:
    by_prefix: dict[str, type[BaseModel]] = {}
    for section in sections:
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


def _configuration_files(package: str, profile: str | None) -> list[Traversable]:
    directory = files(package)
    base = directory.joinpath(BASE_FILE)
    if not base.is_file():
        raise ConfigurationFileNotFoundError(f"{package} has no {BASE_FILE}: it holds every value of the application.")
    if profile is None:
        return [base]
    profile_file = directory.joinpath(f"application-{profile}.toml")
    if not profile_file.is_file():
        raise ConfigurationFileNotFoundError(
            f"{PROFILE_VARIABLE}={profile}, but {package} has no application-{profile}.toml."
        )
    return [base, profile_file]


def _root_model(sections_by_prefix: dict[str, type[BaseModel]], toml_files: list[Traversable]) -> type[BaseSettings]:
    class ConfigurationSources(BaseSettings):
        model_config = SettingsConfigDict(env_prefix="", env_nested_delimiter="__", extra="forbid", frozen=True)

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
            # Only the environment and the files: no initial values, no .env file, no secrets directory.
            return env_settings, TomlConfigSettingsSource(settings_cls, toml_file=toml_files, deep_merge=True)

    fields: dict[str, Any] = {prefix: (section, ...) for prefix, section in sections_by_prefix.items()}
    root: type[BaseSettings] = create_model("Configuration", __base__=ConfigurationSources, **fields)
    return root
