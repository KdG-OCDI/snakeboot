from abc import ABC, abstractmethod
from collections.abc import Callable


class TaskDecorator(ABC):
    """Wraps every piece of work a background thread does, like Spring's `TaskDecorator`.

    A scheduled method or a message is handled outside a request, so nothing prepares and tidies up around it as a
    request would. `snakeboot.django_application` provides one that gives each piece of work usable database
    connections, as Django does around a request.
    """

    @abstractmethod
    def decorate(self, task: Callable[[], None]) -> Callable[[], None]:
        """Returns `task` with whatever must happen before and after it."""
