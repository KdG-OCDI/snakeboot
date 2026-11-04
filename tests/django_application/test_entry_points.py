"""`run` and `wsgi_application` name the application, and snakeboot's settings module builds its settings."""

import importlib
import os
import sys
from types import ModuleType

import pytest
from django.core.exceptions import ImproperlyConfigured

from snakeboot.django_application import APPLICATION_VARIABLE, SETTINGS_MODULE, entry_points, run, wsgi_application
from snakeboot.django_application.entry_points import application_named_in_environment
from tests.django_application.service.applications import ServiceApplication

SERVICE_APPLICATION = "tests.django_application.service.applications.ServiceApplication"


@pytest.fixture(autouse=True)
def no_named_application(monkeypatch: pytest.MonkeyPatch) -> None:
    # setenv, not delenv: monkeypatch restores only what it changed, and run() sets both variables.
    monkeypatch.setenv(APPLICATION_VARIABLE, "")
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "tests.django_settings")


def test_run_names_the_application_and_runs_the_command(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(entry_points, "execute_from_command_line", commands.append)

    run(ServiceApplication, ["manage.py", "check"])

    assert commands == [["manage.py", "check"]]
    assert application_named_in_environment() is ServiceApplication
    assert os.environ["DJANGO_SETTINGS_MODULE"] == SETTINGS_MODULE


def test_wsgi_application_names_the_application_too(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = object()
    monkeypatch.setattr(entry_points, "get_wsgi_application", lambda: handler)

    assert wsgi_application(ServiceApplication) is handler
    assert application_named_in_environment() is ServiceApplication


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
    assert settings.ROOT_URLCONF == "snakeboot.rest.urls"
