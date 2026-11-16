"""A quicker start of wireup's container, until wireup has it itself (maldoinc/wireup#154).

wireup 2.13 decides for every component whether it, or anything it depends on, is built asynchronously, and walks
the dependencies of each one again wherever another component shares them. In an application of some three hundred
components that is millions of steps, three quarters of every start: the server, each command and each test.
"""

from collections.abc import Hashable
from importlib.metadata import version
from typing import Any, Final

from wireup.ioc.registry import ContainerRegistry
from wireup.ioc.types import get_container_object_id

SLOW_WIREUP_VERSIONS: Final = "2.13."
"""How the versions of wireup begin whose walk snakeboot replaces: the ones it was read against."""


def remember_which_components_are_async() -> bool:
    """Makes wireup decide once per component whether it is built asynchronously; tells whether it changed wireup.

    The answers are wireup's own: a component is asynchronous when its factory is, or when one of its dependencies
    is. Another version of wireup than `SLOW_WIREUP_VERSIONS` is left as it is.
    """
    if not version("wireup").startswith(SLOW_WIREUP_VERSIONS):
        return False
    ContainerRegistry._update_factories_async_flag = _update_factories_async_flag  # type: ignore[assignment, method-assign]  # reason: replaces wireup's own walk
    return True


def _update_factories_async_flag(registry: ContainerRegistry) -> None:
    known: dict[Hashable, bool] = {}
    for implementation, qualifiers in registry.impls.items():
        for qualifier in qualifiers:
            key = get_container_object_id(implementation, qualifier)
            registry.factories[key].is_async = _is_async(registry, key, known)


def _is_async(registry: ContainerRegistry, key: Any, known: dict[Hashable, bool]) -> bool:
    if key not in known:
        factory = registry.factories[key]
        known[key] = factory.is_async or any(
            _is_async(registry, _key_of(registry, dependency), known)
            for dependency in registry.dependencies[factory.factory].values()
            if not dependency.is_parameter
        )
    return known[key]


def _key_of(registry: ContainerRegistry, dependency: Any) -> Any:
    implementation = registry.get_implementation(dependency.klass, dependency.qualifier_value)
    return get_container_object_id(implementation, dependency.qualifier_value)
