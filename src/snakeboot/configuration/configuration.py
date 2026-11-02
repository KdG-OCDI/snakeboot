from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import ModuleType
from typing import Final

from pydantic import BaseModel
from wireup import injectable

from snakeboot.configuration.configuration_properties import prefix_of

INJECTABLES_MODULE: Final = "snakeboot.configuration.loaded_sections"


@dataclass(frozen=True, slots=True)
class Configuration:
    """What `load_configuration` read: the active profile and one validated, immutable object per section.

    Composition reads the sections Django itself needs with `get`, and hands every section to wireup with
    `injectables`: an adapter then asks for its section by type, like a `@ConfigurationProperties` bean.
    """

    profile: str | None
    sections: Mapping[type[BaseModel], BaseModel]

    def get[S: BaseModel](self, section: type[S]) -> S:
        """Returns the loaded object of `section`."""
        loaded = self.sections.get(section)
        if not isinstance(loaded, section):
            raise LookupError(
                f"{section.__name__} is not a section of this configuration: pass it to load_configuration."
            )
        return loaded

    def injectables(self) -> list[ModuleType]:
        """Returns a module with one wireup provider per section, for `WireupSettings(injectables=[...])`.

        The list is empty when there are no sections.
        """
        if not self.sections:
            return []
        module = ModuleType(INJECTABLES_MODULE, "The sections of the configuration, provided by type.")
        module.__file__ = f"<{INJECTABLES_MODULE}>"  # wireup only reads the members of a module with a file
        for section, loaded in self.sections.items():
            provider = _provider_of(section, loaded)
            setattr(module, provider.__name__, provider)
        return [module]


def _provider_of(section: type[BaseModel], loaded: BaseModel) -> Callable[[], BaseModel]:
    def provide() -> BaseModel:
        return loaded

    provide.__name__ = provide.__qualname__ = f"provide_{prefix_of(section)}_properties"
    provide.__annotations__ = {"return": section}
    return injectable(provide)
