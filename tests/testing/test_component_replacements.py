"""`@test_component` registers a class of the tests as the replacement of a component, one per component."""

from typing import Any

import pytest

from snakeboot.testing import InvalidTestComponentError, test_component
from snakeboot.testing import component_replacements as replacements_module
from snakeboot.testing.component_replacements import replacing_components


class Mailer:
    pass


@pytest.fixture(autouse=True)
def no_test_components(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test registers into an empty registry, so the notebook's own test components stay out of it."""
    registry: dict[Any, type] = {}
    monkeypatch.setattr(replacements_module, "_REPLACEMENTS", registry)


def test_a_test_component_is_registered_by_what_it_replaces() -> None:
    @test_component(replaces=Mailer)
    class OutboxMailer(Mailer):
        pass

    assert replacing_components() == {Mailer: OutboxMailer}


def test_two_test_components_for_one_component_stop_the_start() -> None:
    @test_component(replaces=Mailer)
    class OutboxMailer(Mailer):
        pass

    with pytest.raises(InvalidTestComponentError, match=r"OutboxMailer and \S+SilentMailer both replace Mailer"):

        @test_component(replaces=Mailer)
        class SilentMailer(Mailer):
            pass


def test_one_class_registered_twice_is_one_test_component() -> None:
    class OutboxMailer(Mailer):
        pass

    test_component(replaces=Mailer)(OutboxMailer)
    test_component(replaces=Mailer)(OutboxMailer)

    assert replacing_components() == {Mailer: OutboxMailer}


def test_pytest_does_not_take_the_decorator_for_a_test() -> None:
    assert getattr(test_component, "__test__", True) is False
