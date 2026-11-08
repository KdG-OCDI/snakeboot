from argparse import ArgumentParser, Namespace
from typing import override

from snakeboot.command_line import CommandLineError, CommandLineRunner


class Journal:
    """Stands in for a port: remembers what the commands did."""

    def __init__(self) -> None:
        self.entries: list[str] = []


class GreetCommand(CommandLineRunner, command="greet"):
    """Greets someone by name.

    Says hello, as often as asked.
    """

    def __init__(self, journal: Journal) -> None:
        self._journal = journal

    @classmethod
    @override
    def add_arguments(cls, parser: ArgumentParser) -> None:
        parser.add_argument("--name", required=True)
        parser.add_argument("--times", type=int, default=1)

    @override
    def run(self, arguments: Namespace) -> None:
        self._journal.entries.extend(f"Hallo {arguments.name}" for _ in range(arguments.times))


class RefuseCommand(CommandLineRunner, command="refuse"):
    """Refuses to do anything."""

    @override
    def run(self, arguments: Namespace) -> None:
        raise CommandLineError("There is nothing to do.")


class SilentCommand(CommandLineRunner, command="silent-night"):
    @override
    def run(self, arguments: Namespace) -> None:
        pass
