"""Registers the one TaskScheduler with wireup, so no application has to.

Part of snakeboot's auto-configuration (`SNAKEBOOT_AUTO_CONFIGURATION`): an application without `@scheduled` methods
has a scheduler that starts no thread.
"""

from typing import Annotated

from wireup import Inject, injectable

from snakeboot.configuration import CONFIGURATION_KEY, Configuration, SchedulingProperties
from snakeboot.lifecycle.application_components import ApplicationComponents
from snakeboot.lifecycle.lifecycle import Lifecycle
from snakeboot.lifecycle.task_decorator import TaskDecorator
from snakeboot.scheduling.task_scheduler import TaskScheduler


@injectable(as_type=Lifecycle, qualifier="snakeboot.scheduling.TaskScheduler")
def task_scheduler(
    components: ApplicationComponents,
    task_decorator: TaskDecorator,
    configuration: Annotated[Configuration, Inject(config=CONFIGURATION_KEY)],
) -> TaskScheduler:
    """Provides the scheduler; `[scheduling] auto_startup = false` keeps its thread from starting."""
    return TaskScheduler(components, task_decorator, auto_startup=auto_startup_of(configuration))


def auto_startup_of(configuration: Configuration) -> bool:
    """Whether scheduled methods run in this process: `[scheduling] auto_startup`, or yes without the section."""
    try:
        return configuration.get(SchedulingProperties).auto_startup
    except LookupError:
        return True
