"""wireup decides once per component whether it is built asynchronously (maldoinc/wireup#154)."""

from typing import Any

import wireup
from wireup.ioc.registry import ContainerRegistry
from wireup.ioc.types import get_container_object_id

from snakeboot.application.container_start_up import remember_which_components_are_async

LAYERS = 40
"""Two components per layer, each on both of the next: a walk without a memory takes 2**40 steps."""


@wireup.injectable
class Leaf:
    pass


class AsyncLeaf:
    pass


@wireup.injectable
async def async_leaf() -> AsyncLeaf:
    return AsyncLeaf()


def _layered_on(leaf: type, name: str) -> list[type]:
    """`LAYERS` layers of two components, each depending on both components of the layer below; `leaf` at the end."""
    below: tuple[type, type] = (leaf, leaf)
    components: list[type] = []
    for layer in range(LAYERS):
        left, right = below

        def build(self: Any, first: Any, second: Any) -> None:
            self.parts = (first, second)

        build.__annotations__ = {"first": left, "second": right, "return": None}
        below = (
            type(f"{name}Left{layer}", (), {"__init__": build}),
            type(f"{name}Right{layer}", (), {"__init__": build}),
        )
        components.extend(below)
    return components


def _is_async(container: Any, component: type) -> bool:
    registry: ContainerRegistry = container._registry  # the flag wireup keeps per factory
    return registry.factories[get_container_object_id(component, None)].is_async


def test_the_installed_wireup_is_one_snakeboot_makes_quicker() -> None:
    # When this fails, wireup moved on: read whether it still walks without a memory, and widen or remove the memo.
    assert remember_which_components_are_async()


def test_a_deep_graph_of_shared_dependencies_starts() -> None:
    components = _layered_on(Leaf, "Sync")

    container = wireup.create_sync_container(injectables=[Leaf, *(wireup.injectable(c) for c in components)])

    assert isinstance(container.get(components[-1]), components[-1])
    assert not _is_async(container, components[-1])


def test_whatever_depends_on_an_async_component_is_async_and_nothing_else() -> None:
    on_async = _layered_on(AsyncLeaf, "Async")
    on_sync = _layered_on(Leaf, "Sync")
    injectables = [Leaf, async_leaf, *(wireup.injectable(c) for c in [*on_async, *on_sync])]

    container = wireup.create_async_container(injectables=injectables)

    assert all(_is_async(container, component) for component in on_async)
    assert not any(_is_async(container, component) for component in [Leaf, *on_sync])
