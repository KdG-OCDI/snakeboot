"""`serve`: the application's own web server, like the server Spring Boot embeds.

    python -m myapp serve              # where [server] host and port say, with [server] workers processes
    python -m myapp serve --reload     # restarts when a source file changes, for development

The application needs no asgi.py and names no server: snakeboot starts uvicorn, which builds the application in each
of its processes.
"""

import os
from argparse import ArgumentParser, Namespace
from typing import Final, override

from snakeboot.application import ApplicationContext
from snakeboot.boot.entry_points import APPLICATION_VARIABLE, application_variable_of
from snakeboot.command_line import CommandLineRunner
from snakeboot.configuration import ServerProperties

FACTORY: Final = "snakeboot.boot.entry_points:application_from_environment"
"""What uvicorn calls in each process it starts to get the application, which `SNAKEBOOT_APPLICATION` names."""


class ServeCommand(CommandLineRunner, command="serve"):
    """Serves the REST API and runs the lifecycle, until SIGTERM or Ctrl+C.

    Listens where [server] host and port say, with [server] workers processes, each with the application's own
    listeners and scheduled methods. --reload restarts the server when a source file changes, for development.
    """

    def __init__(self, context: ApplicationContext, server: ServerProperties) -> None:
        self._application = context.application
        self._server = server

    @classmethod
    @override
    def add_arguments(cls, parser: ArgumentParser) -> None:
        parser.add_argument("--reload", action="store_true", help="Restart when a source file changes.")

    @override
    def run(self, arguments: Namespace) -> None:
        import uvicorn  # noqa: PLC0415  # reason: only serve loads the server, not every command

        os.environ[APPLICATION_VARIABLE] = application_variable_of(self._application)
        uvicorn.run(
            FACTORY,
            factory=True,
            host=self._server.host,
            port=self._server.port,
            workers=self._server.workers,
            reload=arguments.reload,
            log_config=None,  # snakeboot configured logging from [server] log_level
        )
