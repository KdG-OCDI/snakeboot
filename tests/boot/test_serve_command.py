"""`serve` starts uvicorn where [server] says, and uvicorn builds the application in each process through a factory."""

import os
from argparse import Namespace
from collections.abc import Iterator
from typing import Any

import pytest
import uvicorn
from fastapi.testclient import TestClient

from snakeboot.application import ApplicationContext
from snakeboot.boot import CONDITIONAL_MODULES, application_from_environment
from snakeboot.boot.entry_points import APPLICATION_VARIABLE
from snakeboot.boot.serve_command import FACTORY, ServeCommand
from snakeboot.configuration import ServerProperties
from snakeboot.sqlalchemy_data import Database
from snakeboot.sqlalchemy_data.testing import in_memory_database
from tests.application.sample_service.sample_service_application import SampleServiceApplication

SAMPLE = "tests.application.sample_service.sample_service_application:SampleServiceApplication"


@pytest.fixture
def context() -> Iterator[ApplicationContext]:
    context = ApplicationContext.of(SampleServiceApplication, CONDITIONAL_MODULES)
    context.refresh({Database: in_memory_database()})
    yield context
    context.close()


@pytest.fixture
def started_servers(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    servers: list[dict[str, Any]] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **options: servers.append({"app": app, **options}))
    monkeypatch.delenv(APPLICATION_VARIABLE, raising=False)
    return servers


def test_serve_is_a_command_of_every_application_with_a_server(context: ApplicationContext) -> None:
    assert isinstance(context.get(ServeCommand), ServeCommand)


def test_serve_starts_uvicorn_where_the_server_section_says(
    context: ApplicationContext, started_servers: list[dict[str, Any]]
) -> None:
    server = context.configuration.get(ServerProperties)

    context.get(ServeCommand).run(Namespace(reload=False))

    [started] = started_servers
    assert (started["app"], started["factory"]) == (FACTORY, True)
    assert (started["host"], started["port"], started["workers"]) == (server.host, server.port, server.workers)
    assert (started["reload"], started["log_config"]) == (False, None)


def test_serve_names_the_application_to_the_processes_uvicorn_starts(
    context: ApplicationContext, started_servers: list[dict[str, Any]]
) -> None:
    context.get(ServeCommand).run(Namespace(reload=True))

    assert os.environ[APPLICATION_VARIABLE] == SAMPLE
    assert started_servers[0]["reload"] is True


def test_the_factory_builds_the_application_the_environment_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(APPLICATION_VARIABLE, SAMPLE)

    with TestClient(application_from_environment()) as client:
        assert client.get("/health/liveness").json() == {"status": "UP"}


@pytest.mark.parametrize("named", ["", "tests.nowhere:Application", f"{SAMPLE}Missing", "os:sep"])
def test_a_name_that_is_no_application_class_stops_the_start(monkeypatch: pytest.MonkeyPatch, named: str) -> None:
    monkeypatch.setenv(APPLICATION_VARIABLE, named)

    with pytest.raises(LookupError, match=APPLICATION_VARIABLE):
        application_from_environment()
