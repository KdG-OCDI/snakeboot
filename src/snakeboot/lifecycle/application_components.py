from abc import ABC, abstractmethod

from snakeboot.component_scan import MarkedMethod


class ApplicationComponents(ABC):
    """What a `Lifecycle` component needs to know of the application: the slice of Spring's `ApplicationContext`
    that finds annotated methods and hands out beans.

    The scheduler and the message listeners use it to find the methods their decorators marked and the components
    those methods belong to. `snakeboot.django_application` provides it from the component scan and wireup's
    container; tests give a stand-in.
    """

    @abstractmethod
    def methods_marked[M](self, marker: str, mapping_type: type[M]) -> list[MarkedMethod[M]]:
        """Returns every method of the component scan that carries `marker` with a `mapping_type`."""

    @abstractmethod
    def get[T](self, component_type: type[T]) -> T:
        """Returns the component of `component_type`; raises LookupError when the container has none."""
