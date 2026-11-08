"""`run` runs the command its first argument names, and its help lists every command, snakeboot's own included."""

import pytest

from snakeboot.boot import run
from snakeboot.command_line import InvalidCommandLineRunnerError
from tests.application.sample_service.sample_service_application import (
    ClashingCommandsServiceApplication,
    SampleServiceApplication,
)
from tests.command_line.sample_commands.applications import (
    AmbiguousCommandsApplication,
    ApplicationWithoutCommands,
    CommandsApplication,
)


def test_runs_the_command_its_first_argument_names(capsys: pytest.CaptureFixture[str]) -> None:
    run(CommandsApplication, ["myapp", "silent-night"])

    assert capsys.readouterr().err == ""


def test_a_command_line_error_ends_the_process_with_status_1(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        run(CommandsApplication, ["myapp", "refuse"])

    assert stopped.value.code == 1
    assert capsys.readouterr().err == "myapp refuse: There is nothing to do.\n"


def test_help_of_a_command_is_its_own_help_and_builds_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        run(CommandsApplication, ["myapp", "help", "greet"])  # greet needs a Journal the container lacks

    assert stopped.value.code == 0
    assert capsys.readouterr().out.startswith("usage: myapp greet [-h] --name NAME")


def test_the_help_lists_the_application_s_commands_and_snakeboot_s(capsys: pytest.CaptureFixture[str]) -> None:
    run(CommandsApplication, ["myapp", "help"])

    help_text = capsys.readouterr().out
    assert help_text.startswith("usage: myapp <command> [arguments]\n")
    assert "\n[application]\n    greet " in help_text
    assert "\n[snakeboot]\n    run_lifecycle " in help_text
    assert "\n    serve " in help_text


def test_without_a_command_the_help_answers(capsys: pytest.CaptureFixture[str]) -> None:
    run(ApplicationWithoutCommands, ["myapp"])

    assert "[snakeboot]" in capsys.readouterr().out


def test_with_a_database_the_schema_s_commands_are_there(capsys: pytest.CaptureFixture[str]) -> None:
    run(SampleServiceApplication, ["myapp", "help"])

    help_text = capsys.readouterr().out
    assert "    count_games " in help_text
    assert "    migrate " in help_text
    assert "    make_migration " in help_text


def test_a_command_nobody_knows_stops_with_status_2(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        run(CommandsApplication, ["myapp", "fly"])

    assert stopped.value.code == 2
    assert capsys.readouterr().err.startswith("myapp: unknown command 'fly'\n")


def test_python_m_names_the_package_in_the_help(capsys: pytest.CaptureFixture[str]) -> None:
    run(CommandsApplication, ["C:/somewhere/__main__.py", "help"])

    assert capsys.readouterr().out.startswith("usage: python -m tests.command_line.sample_commands <command>")


def test_two_commands_of_one_name_stop_the_start() -> None:
    with pytest.raises(InvalidCommandLineRunnerError, match="Ambiguous command"):
        run(AmbiguousCommandsApplication, ["myapp", "help"])


def test_a_command_named_like_one_of_snakeboot_s_stops_the_start() -> None:
    with pytest.raises(InvalidCommandLineRunnerError, match="Ambiguous command: 'migrate'"):
        run(ClashingCommandsServiceApplication, ["myapp", "help"])
