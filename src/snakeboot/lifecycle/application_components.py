from abc import ABC, abstractmethod
from collections.abc import Callable

from snakeboot.component_scan import MarkedMethod


class ApplicationComponents(ABC):
    """What snakeboot's own components need to know of the application: the slice of Spring's `ApplicationContext`
    that finds annotated classes and methods and hands out beans.

    The scheduler and the message listeners use it to find the methods their decorators marked and the components
    those methods belong to; a persistence binding finds the entities with it. `snakeboot.application` provides it
    from the component scan and wireup's container; tests give a stand-in.
    """

    @abstractmethod
    def classes_marked(self, marker: str) -> list[type]:
        """Returns every class of the component scan that a decorator marked with `marker`."""

    @abstractmethod
    def methods_marked[M](self, marker: str, mapping_type: type[M]) -> list[MarkedMethod[M]]:
        """Returns every method of the component scan that carries `marker` with a `mapping_type`."""

    @abstractmethod
    def get[T](self, component_type: Callable[..., T]) -> T:
        """Returns the component of `component_type`; raises LookupError when the container has none.

        `component_type` is a class, abstract ones and Protocols included: a port or a repository interface.
        """
