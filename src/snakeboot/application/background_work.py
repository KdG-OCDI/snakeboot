"""What threads outside a request need: a `TaskDecorator` around each piece of work.

Part of every application's container (`APPLICATION_AUTO_CONFIGURATION`), for the scheduler and the message
listeners. The database's connection pool tests a connection before it lends it, so a task needs nothing around it.
"""

from collections.abc import Callable
from typing import override

from wireup import injectable

from snakeboot.lifecycle.task_decorator import TaskDecorator


@injectable(as_type=TaskDecorator)
class PlainTaskDecorator(TaskDecorator):
    """Runs each piece of work as it is, like Spring without a `TaskDecorator`."""

    @override
    def decorate(self, task: Callable[[], None]) -> Callable[[], None]:
        return task
