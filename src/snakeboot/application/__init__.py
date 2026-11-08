"""The application context: snakeboot's start, in no framework's terms, like Spring's `ApplicationContext`.

    context = ApplicationContext.start(MyApplication, conditional)   # configuration, container, transactions
    context.get(GameRepository)

It reads the configuration of the application class, builds wireup's container from the modules of the component
scan, installs the transaction manager of `@transactional` when there is a database, and runs the application's
commands (`run_application`). Which module joins the container for which table, a web framework or a database
included, `snakeboot.boot` says: this package knows wireup and snakeboot's own libraries, and no framework.
"""

from snakeboot.application.application_context import (
    APPLICATION_AUTO_CONFIGURATION,
    OPTIONAL_SECTIONS,
    ApplicationContext,
    ConditionalModules,
)
from snakeboot.application.command_line_application import run_application

__all__ = [
    "APPLICATION_AUTO_CONFIGURATION",
    "OPTIONAL_SECTIONS",
    "ApplicationContext",
    "ConditionalModules",
    "run_application",
]
