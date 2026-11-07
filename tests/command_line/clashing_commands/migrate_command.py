from argparse import Namespace
from typing import override

from snakeboot.command_line import CommandLineRunner


class MigrateCommand(CommandLineRunner, command="migrate"):
    """Has the name of one of Django's own commands."""

    @override
    def run(self, arguments: Namespace) -> None: ...
