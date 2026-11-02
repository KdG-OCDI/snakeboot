import re
from collections.abc import Callable
from typing import Final

from pydantic import BaseModel

from snakeboot.configuration.configuration_errors import InvalidConfigurationPropertiesError

PREFIX_ATTRIBUTE: Final = "__configuration_properties_prefix__"
_PREFIX: Final = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")


def configuration_properties[M: type[BaseModel]](prefix: str) -> Callable[[M], M]:
    """Binds a Pydantic model to the table `[prefix]`, like Spring's `@ConfigurationProperties(prefix = ...)`.

    The model receives the table `[prefix]` of `application.toml`, merged with the active profile and the
    environment variables `PREFIX__FIELD__SUBFIELD` (`CHATBOT__LLM__MODEL` sets `chatbot.llm.model`). The
    prefix is one lowercase name with single underscores: a double underscore separates the levels of an
    environment variable.
    """
    if not _PREFIX.fullmatch(prefix):
        raise InvalidConfigurationPropertiesError(
            f"A configuration prefix is one lowercase name with single underscores, got {prefix!r}."
        )

    def declare(model: M) -> M:
        if not _is_pydantic_model(model):
            raise InvalidConfigurationPropertiesError(
                f"@configuration_properties marks a Pydantic model, not {model!r}."
            )
        setattr(model, PREFIX_ATTRIBUTE, prefix)
        return model

    return declare


def prefix_of(model: type[BaseModel]) -> str:
    """Returns the prefix `model` was declared with. A subclass does not inherit it: it is another section."""
    prefix = vars(model).get(PREFIX_ATTRIBUTE)
    if not isinstance(prefix, str):
        raise InvalidConfigurationPropertiesError(
            f"{model.__name__} is not marked with @configuration_properties, so it is not a section."
        )
    return prefix


def _is_pydantic_model(candidate: object) -> bool:
    return isinstance(candidate, type) and issubclass(candidate, BaseModel)
