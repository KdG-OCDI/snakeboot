"""What the scheduler gets from the application, as tests give it."""

from collections.abc import Callable
from typing import override

from snakeboot.component_scan import ComponentScan, MarkedMethod
from snakeboot.lifecycle import ApplicationComponents, TaskDecorator


class ScannedComponents(ApplicationComponents):
    """Stands in for the application context: one package scanned, and the components the test hands it."""

    def __init__(self, package: str, *components: object) -> None:
        self._scan = ComponentScan((package,), auto_configuration=())
        self._components = {type(component): component for component in components}

    @override
    def classes_marked(self, marker: str) -> list[type]:
        return self._scan.classes_marked(marker)

    @override
    def methods_marked[M](self, marker: str, mapping_type: type[M]) -> list[MarkedMethod[M]]:
        return self._scan.methods_marked(marker, mapping_type)

    @override
    def get[T](self, component_type: Callable[..., T]) -> T:
        if component_type not in self._components:
            raise LookupError(repr(component_type))
        component: T = self._components[component_type]  # type: ignore[assignment]
        return component


class CountingTaskDecorator(TaskDecorator):
    """Stands in for what a binding does around a run: counts how often it wrapped one."""

    def __init__(self) -> None:
        self.runs = 0

    @override
    def decorate(self, task: Callable[[], None]) -> Callable[[], None]:
        def counted() -> None:
            self.runs += 1
            task()

        return counted
