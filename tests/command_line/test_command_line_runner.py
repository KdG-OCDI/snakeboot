"""A `CommandLineRunner` is a command of the application: a component that parses its arguments and runs."""

from argparse import ArgumentParser, Namespace
from typing import override

import pytest
import wireup
from wireup import injectable

from snakeboot.command_line import (
    CommandLineRunner,
    InvalidCommandLineRunnerError,
    command_line_runners,
    commands_help,
    run_command,
)
from snakeboot.component_scan import ComponentScan
from tests.command_line.sample_commands.commands import (
    GreetCommand,
    Journal,
    RefuseCommand,
    SilentCommand,
)

SAMPLES = ComponentScan(("tests.command_line.sample_commands.commands",), auto_configuration=())


@pytest.fixture
def journal() -> Journal:
    return Journal()


def test_a_subclass_that_names_its_command_is_a_component() -> None:
    container = wireup.create_sync_container(injectables=[RefuseCommand])

    assert RefuseCommand.command == "refuse"
    assert isinstance(container.get(RefuseCommand), RefuseCommand)


def test_its_constructor_receives_its_dependencies_from_the_container() -> None:
    container = wireup.create_sync_container(injectables=[injectable(Journal), GreetCommand])

    command = container.get(GreetCommand)
    command.run(Namespace(name="Ann", times=1))

    assert container.get(Journal).entries == ["Hallo Ann"]


def test_an_abstract_subclass_without_a_command_is_a_base() -> None:
    class Base(CommandLineRunner):
        pass

    assert "__wireup_registration__" not in vars(Base)


def test_a_subclass_that_runs_but_names_no_command_stops_the_start() -> None:
    with pytest.raises(InvalidCommandLineRunnerError, match="names no command"):

        class Nameless(CommandLineRunner):
            @override
            def run(self, arguments: Namespace) -> None: ...


def test_a_command_that_cannot_be_typed_stops_the_start() -> None:
    with pytest.raises(InvalidCommandLineRunnerError, match="lower case letters"):

        class Shouting(CommandLineRunner, command="Self Play"):
            @override
            def run(self, arguments: Namespace) -> None: ...


def test_arguments_declared_on_the_instance_stop_the_start() -> None:
    with pytest.raises(InvalidCommandLineRunnerError, match=r"Late\.add_arguments must be a @classmethod"):

        class Late(CommandLineRunner, command="late"):
            def add_arguments(self, parser: ArgumentParser) -> None:  # type: ignore[override,explicit-override]
                parser.add_argument("--now")

            @override
            def run(self, arguments: Namespace) -> None: ...


def test_a_command_without_run_stops_the_start() -> None:
    with pytest.raises(InvalidCommandLineRunnerError, match="has no run"):

        class Idle(CommandLineRunner, command="idle"):
            pass


def test_finds_the_commands_of_the_component_scan_by_name() -> None:
    assert command_line_runners(SAMPLES) == {
        "greet": GreetCommand,
        "refuse": RefuseCommand,
        "silent-night": SilentCommand,
    }


def test_a_component_scan_without_commands_has_none() -> None:
    assert command_line_runners(ComponentScan(("snakeboot.transaction",))) == {}


def test_two_commands_of_one_name_stop_the_start() -> None:
    scan = ComponentScan(("tests.command_line.ambiguous_commands",), auto_configuration=())

    with pytest.raises(InvalidCommandLineRunnerError, match="Ambiguous command: 'train'"):
        command_line_runners(scan)


def test_runs_the_command_with_its_parsed_arguments(journal: Journal) -> None:
    exit_status = run_command(
        GreetCommand, ["--name", "Ann", "--times", "2"], program="manage.py", build=lambda: GreetCommand(journal)
    )

    assert exit_status == 0
    assert journal.entries == ["Hallo Ann", "Hallo Ann"]


def test_a_command_line_error_stops_with_its_message_and_status_1(capsys: pytest.CaptureFixture[str]) -> None:
    exit_status = run_command(RefuseCommand, [], program="manage.py", build=RefuseCommand)

    assert exit_status == 1
    assert capsys.readouterr().err == "manage.py refuse: There is nothing to do.\n"


def never_built() -> GreetCommand:
    raise AssertionError("The command was built, though its arguments decided it would not run.")


def test_an_argument_the_command_does_not_know_stops_with_status_2_before_the_command_is_built() -> None:
    with pytest.raises(SystemExit) as stopped:
        run_command(GreetCommand, ["--name", "Ann", "--naem", "Bob"], program="manage.py", build=never_built)

    assert stopped.value.code == 2


def test_the_docstring_is_the_help_of_the_command_which_needs_no_built_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as stopped:
        run_command(GreetCommand, ["--help"], program="python -m myapp", build=never_built)

    help_text = capsys.readouterr().out
    assert stopped.value.code == 0
    assert help_text.startswith("usage: python -m myapp greet [-h] --name NAME [--times TIMES]")
    assert "Greets someone by name.\n\nSays hello, as often as asked." in help_text


def test_the_help_of_the_program_lists_every_command_with_its_first_line() -> None:
    assert commands_help(command_line_runners(SAMPLES)).splitlines() == [
        "",
        "[application]",
        "    greet         Greets someone by name.",
        "    refuse        Refuses to do anything.",
        "    silent-night",
    ]


def test_an_application_without_commands_adds_nothing_to_the_help() -> None:
    assert commands_help({}) == ""
