from abc import ABC, abstractmethod
from collections.abc import Callable


class TaskDecorator(ABC):
    """Wraps every piece of work a background thread does, like Spring's `TaskDecorator`.

    A scheduled method or a message is handled outside a request, so nothing prepares and tidies up around it as a
    request would. `snakeboot.application` provides one that runs each piece of work as it is; a binding that needs
    something around each one, as a web framework does around a request, provides its own.
    """

    @abstractmethod
    def decorate(self, task: Callable[[], None]) -> Callable[[], None]:
        """Returns `task` with whatever must happen before and after it."""
