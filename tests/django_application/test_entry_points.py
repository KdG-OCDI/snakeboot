"""`run`, `wsgi_application` and `asgi_application` name the application and start it on snakeboot's settings;
`run` runs the application's own commands too."""

import importlib
import os
import sys
from types import ModuleType
from typing import ClassVar

import pytest
from django.core.exceptions import ImproperlyConfigured

from snakeboot.command_line import InvalidCommandLineRunnerError
from snakeboot.django_application import (
    APPLICATION_VARIABLE,
    SETTINGS_MODULE,
    asgi_application,
    background_work,
    entry_points,
    run,
    wsgi_application,
)
from snakeboot.django_application.entry_points import application_named_in_environment
from snakeboot.lifecycle import LifecycleAsgiApplication
from tests.command_line.sample_commands.applications import (
    AmbiguousCommandsApplication,
    ApplicationWithoutCommands,
    ClashingCommandsApplication,
    CommandsApplication,
)
from tests.command_line.sample_commands.commands import GreetCommand, Journal
from tests.django_application.service.applications import ServiceApplication

SERVICE_APPLICATION = "tests.django_application.service.applications.ServiceApplication"


@pytest.fixture(autouse=True)
def no_named_application(monkeypatch: pytest.MonkeyPatch) -> None:
    # setenv, not delenv: monkeypatch restores only what it changed, and run() sets both variables.
    monkeypatch.setenv(APPLICATION_VARIABLE, "")
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "tests.django_settings")


class RecordingUtility:
    """Stands in for Django's ManagementUtility: records what it was asked to run, and under which program."""

    executed: ClassVar[list[tuple[list[str], str]]] = []

    def __init__(self, argv: list[str]) -> None:
        self.argv = argv
        self.prog_name = "unset"

    def execute(self) -> None:
        RecordingUtility.executed.append((self.argv, self.prog_name))


@pytest.fixture
def django_commands(monkeypatch: pytest.MonkeyPatch) -> list[tuple[list[str], str]]:
    """Django has started already (pytest-django), and runs no command: it records them."""
    monkeypatch.setattr(entry_points, "setup", lambda: None)
    monkeypatch.setattr(entry_points, "ManagementUtility", RecordingUtility)
    RecordingUtility.executed = []
    return RecordingUtility.executed


def test_run_names_the_application_and_runs_the_command(django_commands: list[tuple[list[str], str]]) -> None:
    run(ServiceApplication, ["manage.py", "check"])

    assert django_commands == [(["manage.py", "check"], "manage.py")]
    assert application_named_in_environment() is ServiceApplication
    assert os.environ["DJANGO_SETTINGS_MODULE"] == SETTINGS_MODULE


def test_django_starts_before_anyone_asks_it_for_its_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    # Django caches its first answer, and before its apps are ready that answer holds no command of an app.
    journal: list[str] = []
    monkeypatch.setattr(entry_points, "setup", lambda: journal.append("setup"))

    def get_commands() -> dict[str, str]:
        journal.append("get_commands")
        return {}

    monkeypatch.setattr(entry_points, "get_commands", get_commands)
    monkeypatch.setattr(entry_points, "ManagementUtility", RecordingUtility)

    run(ServiceApplication, ["manage.py", "run_lifecycle"])

    assert journal[0] == "setup"


def test_a_command_of_django_s_apps_is_left_to_django(django_commands: list[tuple[list[str], str]]) -> None:
    run(ServiceApplication, ["manage.py", "run_lifecycle"])

    assert django_commands == [(["manage.py", "run_lifecycle"], "manage.py")]


def test_the_help_of_python_m_names_the_package_not_django(django_commands: list[tuple[list[str], str]]) -> None:
    run(ServiceApplication, ["/srv/service/__main__.py", "help"])

    assert django_commands == [(["/srv/service/__main__.py", "help"], "python -m tests.django_application.service")]


def test_wsgi_application_names_the_application_too(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = object()
    monkeypatch.setattr(entry_points, "get_wsgi_application", lambda: handler)

    assert wsgi_application(ServiceApplication) is handler
    assert application_named_in_environment() is ServiceApplication


def test_asgi_application_names_the_application_and_runs_the_lifecycle_around_django(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = object()
    monkeypatch.setattr(entry_points, "get_asgi_application", lambda: handler)

    application = asgi_application(ServiceApplication)

    assert isinstance(application, LifecycleAsgiApplication)
    assert application.handler is handler
    assert application_named_in_environment() is ServiceApplication
    assert os.environ["DJANGO_SETTINGS_MODULE"] == SETTINGS_MODULE


def test_without_a_named_application_the_start_stops() -> None:
    with pytest.raises(ImproperlyConfigured, match="names no application class"):
        application_named_in_environment()


def test_a_name_that_is_no_class_stops_the_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(APPLICATION_VARIABLE, "tests.django_application.service.applications.application_root")

    with pytest.raises(ImproperlyConfigured, match="names no application class"):
        application_named_in_environment()


def test_the_settings_module_holds_the_settings_of_the_named_application(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(APPLICATION_VARIABLE, SERVICE_APPLICATION)
    monkeypatch.delitem(sys.modules, SETTINGS_MODULE, raising=False)

    settings: ModuleType = importlib.import_module(SETTINGS_MODULE)

    assert settings.APPLICATION is ServiceApplication
    assert settings.SECRET_KEY == "test-only-secret"
    assert settings.ROOT_URLCONF == "snakeboot.django_ninja.urls"


class StartedContainer:
    """Stands in for wireup's container of the started application: it builds what it is asked for."""

    def __init__(self, journal: Journal) -> None:
        self._journal = journal

    def _synchronous_get(self, component_type: type) -> object:
        return component_type(self._journal) if component_type is GreetCommand else component_type()


@pytest.fixture
def journal(monkeypatch: pytest.MonkeyPatch, django_commands: list[tuple[list[str], str]]) -> Journal:
    """The commands of the application come from a stand-in container."""
    journal = Journal()
    monkeypatch.setattr(background_work, "get_app_container", lambda: StartedContainer(journal))
    return journal


def test_run_runs_the_command_line_runner_its_first_argument_names(
    journal: Journal, django_commands: list[tuple[list[str], str]]
) -> None:
    run(CommandsApplication, ["manage.py", "greet", "--name", "Ann"])

    assert journal.entries == ["Hallo Ann"]
    assert django_commands == []


def test_a_command_line_error_ends_the_process_with_status_1(journal: Journal) -> None:
    with pytest.raises(SystemExit) as stopped:
        run(CommandsApplication, ["manage.py", "refuse"])

    assert stopped.value.code == 1


def test_help_of_a_command_is_its_own_help(journal: Journal, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        run(CommandsApplication, ["/srv/myapp/__main__.py", "help", "greet"])

    assert capsys.readouterr().out.startswith("usage: python -m tests.command_line.sample_commands greet")


def test_the_help_of_the_program_lists_the_commands_after_django_s(
    journal: Journal, django_commands: list[tuple[list[str], str]], capsys: pytest.CaptureFixture[str]
) -> None:
    run(CommandsApplication, ["manage.py"])

    assert django_commands == [(["manage.py"], "manage.py")]
    assert "[application]\n    greet " in capsys.readouterr().out


def test_a_command_nobody_knows_is_left_to_django(
    journal: Journal, django_commands: list[tuple[list[str], str]]
) -> None:
    run(CommandsApplication, ["manage.py", "nonsense"])

    assert django_commands == [(["manage.py", "nonsense"], "manage.py")]


def test_an_application_without_commands_runs_django_s(
    journal: Journal, django_commands: list[tuple[list[str], str]], capsys: pytest.CaptureFixture[str]
) -> None:
    run(ApplicationWithoutCommands, ["manage.py", "help"])

    assert django_commands == [(["manage.py", "help"], "manage.py")]
    assert "[application]" not in capsys.readouterr().out


def test_a_command_with_the_name_of_one_of_django_s_stops_the_start(journal: Journal) -> None:
    with pytest.raises(ImproperlyConfigured, match="migrate: Django has a command of that name already"):
        run(ClashingCommandsApplication, ["manage.py", "help"])


def test_two_commands_of_one_name_stop_the_start(journal: Journal) -> None:
    with pytest.raises(InvalidCommandLineRunnerError, match="Ambiguous command"):
        run(AmbiguousCommandsApplication, ["manage.py", "train"])
