"""`@application_test` marks a test, and hides the parameters its application fills from pytest's fixtures."""

import inspect
from collections.abc import Callable

import pytest

from snakeboot.testing import ApplicationTest, Autowired, MockComponent, SpyComponent, application_test
from snakeboot.testing.application_marker import (
    APPLICATION_TEST_FIXTURE,
    application_test_of,
    injected_fields_of,
    injected_parameters_of,
)
from snakeboot.testing.injection import Injection, InjectionPoint


class Clock:
    pass


class Mailer:
    pass


def parameters_of(test: Callable[..., object]) -> list[str]:
    return list(inspect.signature(test).parameters)


def test_a_function_asks_pytest_for_the_application_instead_of_what_it_injects() -> None:
    def check(clock: Autowired[Clock], tmp_path: object) -> None:
        pass

    marked = application_test(check)

    assert parameters_of(marked) == ["tmp_path", APPLICATION_TEST_FIXTURE]
    assert injected_parameters_of(marked) == {"clock": InjectionPoint(Injection.COMPONENT, Clock)}
    assert application_test_of(marked) == ApplicationTest()


def test_the_wrapper_hands_the_injected_values_to_the_test() -> None:
    def check(clock: Autowired[Clock], tmp_path: object) -> object:
        return clock, tmp_path

    marked: Callable[..., object] = application_test(check)
    clock = Clock()

    assert marked(tmp_path="here", **{APPLICATION_TEST_FIXTURE: {"clock": clock}}) == (clock, "here")


def test_a_class_has_its_fields_filled_and_the_parameters_of_its_methods() -> None:
    @application_test(profile="test", properties={"notes.max_length": 3})
    class TestNotes:
        clock: Autowired[Clock]
        mailer: MockComponent[Mailer]
        name: str

        def test_with_a_spy(self, mailer: SpyComponent[Mailer]) -> None:
            pass

        def test_without_injection(self, tmp_path: object) -> None:
            pass

    assert injected_fields_of(TestNotes) == {
        "clock": InjectionPoint(Injection.COMPONENT, Clock),
        "mailer": InjectionPoint(Injection.MOCK, Mailer),
    }
    assert parameters_of(TestNotes.test_with_a_spy) == ["self", APPLICATION_TEST_FIXTURE]
    assert parameters_of(TestNotes.test_without_injection) == ["self", "tmp_path"]
    marker = application_test_of(TestNotes)
    assert marker is not None
    environment = marker.environment
    assert (marker.application, environment.profile, dict(environment.properties)) == (
        None,
        "test",
        {"notes.max_length": 3},
    )


def test_only_a_function_or_a_class_is_a_test() -> None:
    with pytest.raises(TypeError, match="marks a test function or a test class"):
        application_test()(42)
