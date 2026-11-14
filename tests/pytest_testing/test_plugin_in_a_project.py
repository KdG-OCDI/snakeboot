"""In a project of its own, a bare `@application_test` finds the application and the test components by itself.

pytester writes the project and runs pytest on it in a process of its own, as an application's own `pytest` runs:
snakeboot's plugin is loaded through its entry point, with no conftest.py and no setting in pyproject.toml.
"""

from pathlib import Path

import pytest

SERVER = """\
[server]
host = "127.0.0.1"
port = 8000
workers = 1
debug = false
allowed_hosts = ["*"]
log_level = "WARNING"
"""

SHOP_APPLICATION = """\
from snakeboot.component_scan import application_root


@application_root
class ShopApplication:
    '''A shop that greets its customers.'''
"""

GREETING = """\
from abc import ABC, abstractmethod

from snakeboot.stereotype import component

from snakeboot.rest import rest_controller, route


class Greeter(ABC):
    @abstractmethod
    def greet(self) -> str: ...


@component(as_type=Greeter)
class FriendlyGreeter(Greeter):
    def greet(self) -> str:
        return "Welcome"


@rest_controller("/greeting")
class GreetingRestController:
    def __init__(self, greeter: Greeter) -> None:
        self._greeter = greeter

    @route.get("")
    def greeting(self) -> dict[str, str]:
        return {"text": self._greeter.greet()}
"""

DOUBLES = """\
from shop.greeting import Greeter
from snakeboot.testing import test_component


@test_component(replaces=Greeter)
class CheerfulGreeter(Greeter):
    def greet(self) -> str:
        return "Hooray"
"""

TESTS = """\
from snakeboot.boot.testing import RestClient
from snakeboot.testing import Autowired, application_test

from doubles import CheerfulGreeter


@application_test
def test_the_application_and_its_test_components_are_found(
    client: Autowired[RestClient], greeter: Autowired[CheerfulGreeter]
) -> None:
    assert client.get("/api/greeting").json() == {"text": "Hooray"}


class NotAComponent:
    pass


@application_test
def test_an_unknown_component_fails_the_set_up(unknown: Autowired[NotAComponent]) -> None:
    raise AssertionError("The test itself never runs.")
"""

BACK_OFFICE = """\
from snakeboot.component_scan import application_root


@application_root
class BackOfficeApplication:
    '''A second application in the same source.'''
"""


def write_shop(directory: Path) -> None:
    shop = directory / "shop"
    shop.mkdir()
    (shop / "__init__.py").write_text("")
    (shop / "application.toml").write_text(SERVER)
    (shop / "shop_application.py").write_text(SHOP_APPLICATION)
    (shop / "greeting.py").write_text(GREETING)
    (directory / "doubles.py").write_text(DOUBLES)
    (directory / "test_shop.py").write_text(TESTS)


def test_a_bare_application_test_finds_the_application_and_the_test_components(pytester: pytest.Pytester) -> None:
    write_shop(pytester.path)

    result = pytester.runpytest_subprocess("-p", "no:cacheprovider")

    result.assert_outcomes(passed=1, errors=1)
    result.stdout.fnmatch_lines(["*The container has no NotAComponent*"])


def test_two_applications_in_the_source_ask_for_a_name(pytester: pytest.Pytester) -> None:
    write_shop(pytester.path)
    (pytester.path / "shop" / "back_office.py").write_text(BACK_OFFICE)

    result = pytester.runpytest_subprocess("-p", "no:cacheprovider", "-k", "are_found")

    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*found 2 (shop.back_office:BackOfficeApplication, shop.shop_application*"])
