"""A process that keeps running prints snakeboot's banner when it starts, like Spring Boot's."""

from argparse import Namespace
from importlib.metadata import version
from io import StringIO

import pytest
import uvicorn

from snakeboot.application import ApplicationContext
from snakeboot.application.banner import banner, print_banner
from snakeboot.boot import CONDITIONAL_MODULES
from snakeboot.boot.serve_command import ServeCommand
from snakeboot.sqlalchemy_data import Database
from snakeboot.sqlalchemy_data.testing import in_memory_database
from tests.application.sample_service.sample_service_application import SampleServiceApplication

CONSOLE_WIDTH = 80


def _printed(properties: dict[str, object]) -> str:
    context = ApplicationContext.of(SampleServiceApplication, CONDITIONAL_MODULES, properties=properties)
    console = StringIO()
    print_banner(context.configuration, console)
    return console.getvalue()


def test_the_banner_names_snakeboot_and_its_version() -> None:
    last_line = banner().rstrip().splitlines()[-1]

    assert last_line.startswith(" :: snakeboot ::")
    assert last_line.endswith(f"(v{version('snakeboot')})")


def test_the_banner_fits_every_console() -> None:
    assert banner().isascii()
    assert all(len(line) <= CONSOLE_WIDTH for line in banner().splitlines())


def test_an_application_prints_it_unless_it_says_otherwise() -> None:
    assert _printed({}) == banner()


def test_banner_false_leaves_it_out() -> None:
    assert _printed({"server.banner": False}) == ""


def test_structured_log_lines_leave_it_out() -> None:
    assert _printed({"logging.format": "ecs"}) == ""


def test_serve_prints_it_once_before_the_server_starts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(uvicorn, "run", lambda app, **options: None)
    context = ApplicationContext.of(SampleServiceApplication, CONDITIONAL_MODULES)
    context.refresh({Database: in_memory_database()})

    try:
        context.get(ServeCommand).run(Namespace(reload=False))
    finally:
        context.close()

    assert capsys.readouterr().err == banner()
