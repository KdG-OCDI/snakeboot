import re
from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace
from typing import Any, ClassVar, Final, override

from wireup import injectable

from snakeboot.command_line.command_line_errors import InvalidCommandLineRunnerError

COMMAND_ATTRIBUTE: Final = "__command_line_runner__"
"""Set on every subclass that names a command, so the component scan finds the commands of the application."""

_COMMAND_NAME: Final = re.compile(r"[a-z][a-z0-9_-]*")


class CommandLineRunner(ABC):
    """A command of the application, like a `CommandLineRunner` bean in Spring Boot.

    Extend it with the name of the command, and the subclass is a component of the container: its constructor
    receives use cases, ports and sections by type, like any adapter. `python -m myapp <command> [arguments]` starts
    the application, parses the arguments with `add_arguments`, and only then builds the command and calls `run`:
    `--help` answers at once, whatever the command depends on. Unlike Spring Boot, which runs every
    CommandLineRunner at each start, an application has as many commands as it likes and the first argument chooses
    one, as with Spring Shell's `@Command`.

        class SelfPlayCommand(CommandLineRunner, command="self_play"):
            '''Lets the AI levels play each other and prints how strong each one is.'''

            def __init__(self, self_play: SelfPlayUseCase) -> None:
                self._self_play = self_play

            @classmethod
            @override
            def add_arguments(cls, parser: ArgumentParser) -> None:
                parser.add_argument("--games", type=int, default=20, help="Games per pairing.")

            @override
            def run(self, arguments: Namespace) -> None:
                print(self._self_play.execute(SelfPlayRequestDTO(games=arguments.games)))

    The docstring of the subclass is the help of the command. A `CommandLineError` stops it with a message and
    exit status 1. Nothing here knows the framework that starts the application.
    """

    command: ClassVar[str] = ""
    """The name typed after the program: lower case letters, digits, `_` and `-`, starting with a letter."""

    @override
    def __init_subclass__(cls, *, command: str = "", **kwargs: Any) -> None:
        """Registers a subclass that names its command as a component; an abstract one without a name is a base."""
        super().__init_subclass__(**kwargs)
        _refuse_arguments_of_an_instance(cls)
        still_abstract = getattr(cls.run, "__isabstractmethod__", False)
        if still_abstract and not command:
            return
        _refuse_invalid_command(cls, command, still_abstract=still_abstract)
        cls.command = command
        setattr(cls, COMMAND_ATTRIBUTE, command)
        injectable(cls)

    @classmethod  # noqa: B027  # reason: a hook a command may leave out
    def add_arguments(cls, parser: ArgumentParser) -> None:
        """Declares the arguments of the command on `parser`, as with argparse; by default it takes none.

        A classmethod: the arguments are parsed before the command is built, so `--help` and a wrong argument need
        nothing the command depends on (a client that connects to a server, say).
        """

    @abstractmethod
    def run(self, arguments: Namespace) -> None:
        """Does the work of the command with the parsed `arguments`."""


def _refuse_arguments_of_an_instance(cls: type) -> None:
    declared = vars(cls).get("add_arguments")
    if declared is not None and not isinstance(declared, classmethod):
        raise InvalidCommandLineRunnerError(
            f"{cls.__qualname__}.add_arguments must be a @classmethod: the arguments are parsed before the command "
            "is built, so --help needs nothing the command depends on."
        )


def _refuse_invalid_command(cls: type, command: str, *, still_abstract: bool) -> None:
    if not command:
        raise InvalidCommandLineRunnerError(
            f"{cls.__qualname__} runs, but names no command: class {cls.__name__}(CommandLineRunner, command=...)."
        )
    if still_abstract:
        raise InvalidCommandLineRunnerError(f"{cls.__qualname__} names the command {command!r}, but has no run.")
    if not _COMMAND_NAME.fullmatch(command):
        raise InvalidCommandLineRunnerError(
            f"{cls.__qualname__} names the command {command!r}: a command is lower case letters, digits, '_' and "
            "'-', starting with a letter."
        )
