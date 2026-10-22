"""The scanner finds every @rest_controller under some packages, once, in a stable order."""

import importlib

from snakeboot.rest import RestControllerScanner
from tests.rest.sample_controllers.greeting_rest_controller import GreetingRestController
from tests.rest.sample_controllers.nested.farewell_rest_controller import FarewellRestController

SAMPLES = "tests.rest.sample_controllers"


def test_finds_controllers_in_a_package_and_its_subpackages_sorted_by_module() -> None:
    assert RestControllerScanner().scan([SAMPLES]) == [GreetingRestController, FarewellRestController]


def test_reports_a_re_exported_controller_only_where_it_is_defined() -> None:
    found = RestControllerScanner().scan([SAMPLES, f"{SAMPLES}.re_export"])

    assert found.count(GreetingRestController) == 1


def test_accepts_a_plain_module() -> None:
    assert RestControllerScanner().scan([f"{SAMPLES}.nested.farewell_rest_controller"]) == [FarewellRestController]


def test_finds_nothing_where_there_are_no_controllers() -> None:
    assert RestControllerScanner().scan(["snakeboot.transaction"]) == []


def test_accepts_module_objects_as_wireup_settings_may_hold_them() -> None:
    module = importlib.import_module(f"{SAMPLES}.nested.farewell_rest_controller")

    assert RestControllerScanner().scan([module]) == [FarewellRestController]
