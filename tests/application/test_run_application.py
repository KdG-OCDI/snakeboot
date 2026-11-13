"""`run` runs the command its first argument names, and its help lists every command, snakeboot's own included."""

import pytest

from snakeboot.boot import run
from snakeboot.command_line import InvalidCommandLineRunnerError
from snakeboot.component_scan import application_root
from snakeboot.configuration import PROFILE_VARIABLE
from tests.application.sample_service.sample_service_application import (
    ClashingCommandsServiceApplication,
    SampleServiceApplication,
)
from tests.application.service_without_secrets.service_without_secrets_application import (
    ServiceWithoutSecretsApplication,
)
from tests.command_line.sample_commands.applications import (
    AmbiguousCommandsApplication,
    ApplicationWithoutCommands,
    CommandsApplication,
)


@application_root(base_packages=("snakeboot.transaction",))
class ApplicationWithoutFiles:
    """An application whose package, tests.application, has no application.toml."""


@pytest.fixture(autouse=True)
def without_the_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts without a profile and without the variables these tests set, whatever the machine has."""
    for variable in (PROFILE_VARIABLE, "DATABASE__PASSWORD", "MAIL__SENDER", "SERVER__PORT"):
        monkeypatch.delenv(variable, raising=False)


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


@pytest.mark.parametrize("argv", [["myapp", "help"], ["myapp"], ["myapp", "--help"]])
def test_the_help_answers_without_a_secret_and_lists_the_commands_of_its_tables(
    capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    run(ServiceWithoutSecretsApplication, argv)  # [database] has no password

    help_text = capsys.readouterr().out
    assert "    migrate " in help_text
    assert "    make_migration " in help_text
    assert "    serve " in help_text


def test_the_help_of_a_command_answers_without_a_secret(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        run(ServiceWithoutSecretsApplication, ["myapp", "help", "migrate"])

    assert stopped.value.code == 0
    assert capsys.readouterr().out.startswith("usage: myapp migrate ")


def test_a_command_without_a_secret_stops_with_status_1_and_names_its_variable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as stopped:
        run(ServiceWithoutSecretsApplication, ["myapp", "migrate"])

    assert stopped.value.code == 1
    assert capsys.readouterr().err == (
        "myapp migrate: database.password is missing: set it in application.toml or DATABASE__PASSWORD\n"
    )


def test_a_value_missing_from_a_section_of_the_application_stops_the_command_alike(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE__PASSWORD", "set-by-the-deployment")

    with pytest.raises(SystemExit) as stopped:
        run(ServiceWithoutSecretsApplication, ["myapp", "migrate"])  # [mail] is read when the container is built

    assert stopped.value.code == 1
    assert capsys.readouterr().err == (
        "myapp migrate: mail.sender is missing: set it in application.toml or MAIL__SENDER\n"
    )


def test_every_problem_of_the_configuration_is_one_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SERVER__PORT", "eighty")

    with pytest.raises(SystemExit) as stopped:
        run(ServiceWithoutSecretsApplication, ["myapp", "serve"])

    assert stopped.value.code == 1
    assert capsys.readouterr().err.splitlines() == [
        "myapp serve: server.port is invalid (Input should be a valid integer, unable to parse string as an "
        "integer): correct it in application.toml or SERVER__PORT",
        "myapp serve: database.password is missing: set it in application.toml or DATABASE__PASSWORD",
    ]


def test_the_help_of_an_application_without_a_database_lists_no_migrate_whatever_its_values(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SERVER__PORT", "eighty")

    run(CommandsApplication, ["myapp", "help"])  # application.toml has [server] only

    help_text = capsys.readouterr().out
    assert "    serve " in help_text
    assert "migrate" not in help_text


def test_an_application_without_its_file_stops_with_status_1_even_for_the_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as stopped:
        run(ApplicationWithoutFiles, ["myapp", "help"])

    assert stopped.value.code == 1
    assert capsys.readouterr().err == (
        "myapp: tests.application has no application.toml: it holds every value of the application.\n"
    )
