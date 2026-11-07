import inspect
import sys
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from collections.abc import Mapping, Sequence

from snakeboot.command_line.command_line_errors import CommandLineError, InvalidCommandLineRunnerError
from snakeboot.command_line.command_line_runner import COMMAND_ATTRIBUTE, CommandLineRunner
from snakeboot.component_scan import ComponentScan


def command_line_runners(component_scan: ComponentScan) -> dict[str, type[CommandLineRunner]]:
    """Returns the commands of the component scan by name; two classes for one name stop the start."""
    runners: dict[str, type[CommandLineRunner]] = {}
    for runner in component_scan.classes_marked(COMMAND_ATTRIBUTE):
        if not issubclass(runner, CommandLineRunner):
            continue
        if (earlier := runners.get(runner.command)) is not None:
            raise InvalidCommandLineRunnerError(
                f"Ambiguous command: {runner.command!r} is run by {earlier.__qualname__} and {runner.__qualname__}."
            )
        runners[runner.command] = runner
    return runners


def run_command(runner: CommandLineRunner, arguments: Sequence[str], *, program: str) -> int:
    """Parses `arguments` for `runner`, runs it and returns the exit status.

    As with argparse, `--help` prints the help of the command and an argument it does not know stops with status 2.
    A `CommandLineError` prints its message to standard error and returns 1.
    """
    parser = ArgumentParser(
        prog=f"{program} {runner.command}",
        description=_help_of(type(runner)),
        formatter_class=RawDescriptionHelpFormatter,  # the docstring keeps its paragraphs
    )
    runner.add_arguments(parser)
    parsed = parser.parse_args(list(arguments))
    try:
        runner.run(parsed)
    except CommandLineError as error:
        sys.stderr.write(f"{parser.prog}: {error}\n")
        return 1
    return 0


def commands_help(runners: Mapping[str, type[CommandLineRunner]]) -> str:
    """Lists the commands of the application with the first line of their help, for the help of the program."""
    if not runners:
        return ""
    width = max(len(command) for command in runners) + 2
    lines = [f"    {command:<{width}}{_summary_of(runners[command])}".rstrip() for command in sorted(runners)]
    return "\n".join(["", "[application]", *lines, ""])


def _help_of(runner_class: type[CommandLineRunner]) -> str | None:
    # The class's own docstring only: inspect.getdoc would fall back on CommandLineRunner's.
    documentation = vars(runner_class).get("__doc__")
    return inspect.cleandoc(documentation) if documentation else None


def _summary_of(runner_class: type[CommandLineRunner]) -> str:
    help_text = _help_of(runner_class)
    return help_text.splitlines()[0] if help_text else ""
