import os
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Final

from snakeboot.application.application_context import ApplicationContext, ConditionalModules, component_scan_of
from snakeboot.command_line import CommandLineRunner, command_line_runners, commands_help, run_command
from snakeboot.component_scan import application_package
from snakeboot.configuration import configuration_problems, sections_with_a_table

HELP: Final = ("help", "--help", "-h")
"""What asks for the help of the program, which lists every command."""

UNKNOWN_COMMAND_STATUS: Final = 2
"""The exit status of a command nobody knows, as argparse exits for an argument it does not know."""

CONFIGURATION_PROBLEM_STATUS: Final = 1
"""The exit status of a command that cannot start because of its configuration, like Spring Boot's failed start."""


def run_application(application: type, argv: Sequence[str] | None, conditional: ConditionalModules) -> None:
    """Runs the command of `application` that the first argument names, like Spring Boot's `SpringApplication.run`.

    `python -m myapp self_play --games 20` runs the `CommandLineRunner` named `self_play`; `help self_play` prints its
    help; `help`, or no command, lists every command, snakeboot's own (`run_lifecycle`, `migrate`) included. Which
    commands there are depends on the tables of the configuration, not on their values, and the arguments are parsed
    before anything is built, so the help answers even when a value is missing or invalid. A command whose
    configuration is invalid stops with one line per problem, naming its key and the variable that sets it, and exit
    status 1, like Spring Boot's failure analysis. A command exits with status 1 on a `CommandLineError`, a command
    nobody knows with status 2.
    """
    arguments = list(argv) if argv is not None else list(sys.argv)
    program = _program_of(application, arguments[0])
    command, command_arguments = _requested_command(arguments)
    with _stopping_on_configuration_problems(program):
        runners = _commands_of(application, conditional)
    if command in HELP:
        sys.stdout.write(_program_help(program, runners))
        return
    runner = runners.get(command)
    if runner is None:
        sys.stderr.write(f"{program}: unknown command {command!r}\n{_program_help(program, runners)}")
        sys.exit(UNKNOWN_COMMAND_STATUS)
    start = _ApplicationStart(application, conditional)
    try:
        with _stopping_on_configuration_problems(f"{program} {command}"):
            exit_status = run_command(runner, command_arguments, program=program, build=lambda: start.built(runner))
    finally:
        start.close()
    if exit_status:
        sys.exit(exit_status)


class _ApplicationStart:
    """Starts the application once a command is built, after its arguments are parsed, and closes it afterwards."""

    def __init__(self, application: type, conditional: ConditionalModules) -> None:
        self._application = application
        self._conditional = conditional
        self._context: ApplicationContext | None = None

    def built[R: CommandLineRunner](self, runner: type[R]) -> R:
        self._context = ApplicationContext.of(self._application, self._conditional)
        self._context.refresh()
        return self._context.get(runner)

    def close(self) -> None:
        if self._context is not None:
            self._context.close()


def _commands_of(application: type, conditional: ConditionalModules) -> dict[str, type[CommandLineRunner]]:
    # The tables decide which commands there are (`migrate` comes with [database]); their values are read when a
    # command is built, so the help needs none of them.
    present = sections_with_a_table(*conditional, package=application_package(application))
    return command_line_runners(component_scan_of(application, conditional, present))


@contextmanager
def _stopping_on_configuration_problems(program: str) -> Iterator[None]:
    # A value that is missing or invalid is no bug: whoever deploys the application reads what to set, not a traceback.
    try:
        yield
    except Exception as error:
        problems = configuration_problems(error)
        if not problems:
            raise
        sys.stderr.writelines(f"{program}: {problem}\n" for problem in problems)
        sys.exit(CONFIGURATION_PROBLEM_STATUS)


def _requested_command(arguments: Sequence[str]) -> tuple[str, list[str]]:
    # `help self_play` asks for what `self_play --help` prints.
    command, *rest = arguments[1:] or ["help"]
    if command == "help" and rest:
        return rest[0], ["--help"]
    return command, rest


def _program_help(program: str, runners: dict[str, type[CommandLineRunner]]) -> str:
    return (
        f"usage: {program} <command> [arguments]\n\n"
        f"Type '{program} help <command>' for the help of a command.\n{commands_help(runners)}"
    )


def _program_of(application: type, script: str) -> str:
    # `python -m myapp` runs myapp/__main__.py: the help names the program as it was typed.
    name = os.path.basename(script)
    return f"python -m {application_package(application)}" if name == "__main__.py" else name
