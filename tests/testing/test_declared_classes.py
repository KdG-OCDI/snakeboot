"""`declared_classes` reads the source: what an architecture test compares with what the scan found."""

from pathlib import Path

from snakeboot.testing import declared_classes, qualified_names
from tests.rest.sample_controllers.greeting_rest_controller import GreetingRestController
from tests.rest.sample_controllers.nested.farewell_rest_controller import FarewellRestController

SAMPLES = Path(__file__).resolve().parents[1] / "rest" / "sample_controllers"


def test_finds_classes_with_the_decorator_called_or_bare_in_every_subpackage() -> None:
    assert declared_classes(SAMPLES, "rest_controller") == {
        "sample_controllers.greeting_rest_controller.GreetingRestController",
        "sample_controllers.nested.farewell_rest_controller.FarewellRestController",
    }
    assert declared_classes(SAMPLES, "rest_controller_advice") == {
        "sample_controllers.greeting_rest_controller.GreetingRestErrorAdvice"
    }


def test_names_modules_from_the_package_directory_down() -> None:
    names = declared_classes(SAMPLES.parent, "rest_controller")

    assert "rest.sample_controllers.nested.farewell_rest_controller.FarewellRestController" in names


def test_a_re_export_is_not_a_declaration() -> None:
    assert not any("re_export" in name for name in declared_classes(SAMPLES, "rest_controller"))


def test_qualified_names_match_the_form_of_declared_classes() -> None:
    assert qualified_names([GreetingRestController, FarewellRestController]) == {
        "tests.rest.sample_controllers.greeting_rest_controller.GreetingRestController",
        "tests.rest.sample_controllers.nested.farewell_rest_controller.FarewellRestController",
    }
