import os
import sys
from collections.abc import Sequence
from typing import Final

from snakeboot.application.application_context import ApplicationContext, ConditionalModules
from snakeboot.command_line import CommandLineRunner, command_line_runners, commands_help, run_command
from snakeboot.component_scan import application_package

HELP: Final = ("help", "--help", "-h")
"""What asks for the help of the program, which lists every command."""

UNKNOWN_COMMAND_STATUS: Final = 2
"""The exit status of a command nobody knows, as argparse exits for an argument it does not know."""


def run_application(application: type, argv: Sequence[str] | None, conditional: ConditionalModules) -> None:
    """Runs the command of `application` that the first argument names, like Spring Boot's `SpringApplication.run`.

    `python -m myapp self_play --games 20` runs the `CommandLineRunner` named `self_play`; `help self_play` prints its
    help; `help`, or no command, lists every command, snakeboot's own (`run_lifecycle`, `migrate`) included. The
    arguments are parsed before the container is built, so the help answers at once. A command exits with status 1
    on a `CommandLineError`, a command nobody knows with status 2.
    """
    arguments = list(argv) if argv is not None else list(sys.argv)
    context = ApplicationContext.of(application, conditional)
    runners = command_line_runners(context.scan)
    program = _program_of(application, arguments[0])
    command, command_arguments = _requested_command(arguments)
    if command in HELP:
        sys.stdout.write(_program_help(program, runners))
        return
    runner = runners.get(command)
    if runner is None:
        sys.stderr.write(f"{program}: unknown command {command!r}\n{_program_help(program, runners)}")
        sys.exit(UNKNOWN_COMMAND_STATUS)
    try:
        exit_status = run_command(runner, command_arguments, program=program, build=lambda: _built(context, runner))
    finally:
        context.close()
    if exit_status:
        sys.exit(exit_status)


def _built[R: CommandLineRunner](context: ApplicationContext, runner: type[R]) -> R:
    context.refresh()
    return context.get(runner)


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
