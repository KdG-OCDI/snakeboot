import re
from types import ModuleType
from typing import Final

from snakeboot.configuration.configuration_errors import InvalidConfigurationPropertiesError
from snakeboot.configuration.section import Section

PREFIX_ATTRIBUTE: Final = "__configuration_properties_prefix__"
PREFIX: Final = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")


def prefix_of(model: type[Section]) -> str:
    """Returns the prefix `model` was declared with. A subclass does not inherit it: it is another section."""
    prefix = vars(model).get(PREFIX_ATTRIBUTE)
    if not isinstance(prefix, str):
        raise InvalidConfigurationPropertiesError(
            f"{model.__name__} is not marked with @configuration_properties, so it is not a section."
        )
    return prefix


def sections_declared_in(module: ModuleType) -> list[type[Section]]:
    """Returns the sections `module` itself declares with `@configuration_properties`, in the order of the file.

    A section that `module` imports belongs to the module that declares it, so a scan finds every section once.
    """
    return [member for member in vars(module).values() if _is_section_declared_in(member, module)]


def _is_section_declared_in(member: object, module: ModuleType) -> bool:
    return (
        isinstance(member, type)
        and issubclass(member, Section)
        and member.__module__ == module.__name__
        and PREFIX_ATTRIBUTE in vars(member)
    )
