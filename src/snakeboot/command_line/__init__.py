"""Technical library: the commands of an application, like Spring Boot's `CommandLineRunner`.

    class TrainCommand(CommandLineRunner, command="train"):     # python -m myapp train --epochs 5
        '''Trains the model on the exported games.'''

        def __init__(self, train: TrainUseCase) -> None: ...   # constructor injection

        @classmethod
        @override
        def add_arguments(cls, parser: ArgumentParser) -> None: ...   # argparse, before anything is built

        @override
        def run(self, arguments: Namespace) -> None: ...

A command is a component of the component scan; `run(MyApplication)` (snakeboot.boot) starts the application and
runs the command that its first argument names, and the help of the program lists every command. It knows wireup
and the component scan, but no framework: commands keep working when snakeboot binds another one.
"""

from snakeboot.command_line.command_line import command_line_runners, commands_help, run_command
from snakeboot.command_line.command_line_errors import CommandLineError, InvalidCommandLineRunnerError
from snakeboot.command_line.command_line_runner import CommandLineRunner

__all__ = [
    "CommandLineError",
    "CommandLineRunner",
    "InvalidCommandLineRunnerError",
    "command_line_runners",
    "commands_help",
    "run_command",
]
