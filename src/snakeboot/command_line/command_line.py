import inspect
import sys
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from collections.abc import Callable, Mapping, Sequence
from typing import Final

from snakeboot.command_line.command_line_errors import CommandLineError, InvalidCommandLineRunnerError
from snakeboot.command_line.command_line_runner import COMMAND_ATTRIBUTE, CommandLineRunner
from snakeboot.component_scan import ComponentScan

SNAKEBOOT_PACKAGE: Final = "snakeboot."
"""Commands from a module below it are snakeboot's own, such as `run_lifecycle` and `migrate`."""


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


def run_command[R: CommandLineRunner](
    runner_class: type[R], arguments: Sequence[str], *, program: str, build: Callable[[], R]
) -> int:
    """Parses `arguments` for `runner_class`, then builds the command with `build`, runs it and returns the status.

    The arguments come first, as Spring Shell reads its options before it calls the command: `--help` prints the
    help and an argument the command does not know stops with status 2, before anything the command depends on is
    built. A `CommandLineError` prints its message to standard error and returns 1. The application builds the
    command from its container; a test builds it with doubles: `build=lambda: SelfPlayCommand(fake_use_case)`.
    """
    parser = ArgumentParser(
        prog=f"{program} {runner_class.command}",
        description=_help_of(runner_class),
        formatter_class=RawDescriptionHelpFormatter,  # the docstring keeps its paragraphs
    )
    runner_class.add_arguments(parser)
    parsed = parser.parse_args(list(arguments))
    try:
        build().run(parsed)
    except CommandLineError as error:
        sys.stderr.write(f"{parser.prog}: {error}\n")
        return 1
    return 0


def commands_help(runners: Mapping[str, type[CommandLineRunner]]) -> str:
    """Lists the commands with the first line of their help, the application's apart from snakeboot's own."""
    width = max((len(command) for command in runners), default=0) + 2
    groups: dict[str, list[str]] = {"application": [], "snakeboot": []}
    for command in sorted(runners):
        runner = runners[command]
        group = "snakeboot" if runner.__module__.startswith(SNAKEBOOT_PACKAGE) else "application"
        groups[group].append(f"    {command:<{width}}{_summary_of(runner)}".rstrip())
    return "".join(_group_help(group, lines) for group, lines in groups.items() if lines)


def _group_help(group: str, lines: list[str]) -> str:
    listed = "\n".join(lines)
    return f"\n[{group}]\n{listed}\n"


def _help_of(runner_class: type[CommandLineRunner]) -> str | None:
    # The class's own docstring only: inspect.getdoc would fall back on CommandLineRunner's.
    documentation = vars(runner_class).get("__doc__")
    return inspect.cleandoc(documentation) if documentation else None


def _summary_of(runner_class: type[CommandLineRunner]) -> str:
    help_text = _help_of(runner_class)
    return help_text.splitlines()[0] if help_text else ""
