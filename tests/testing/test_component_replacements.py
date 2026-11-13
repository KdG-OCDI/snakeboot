"""`@test_component` registers a class of the tests as the replacement of a component, one per component.

Nested in a test class, it holds for that class and the classes nested in it only.
"""

from typing import Any

import pytest

from snakeboot.testing import InvalidTestComponentError, test_component
from snakeboot.testing import component_replacements as replacements_module
from snakeboot.testing.component_replacements import nested_test_components, replacing_components


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


class Printer:
    pass


def test_pytest_does_not_take_a_test_component_for_a_test_class() -> None:
    class TestOutbox:
        @test_component(replaces=Mailer)
        class TestMailer(Mailer):
            def __init__(self, sent: list[str]) -> None:
                self.sent = sent

    assert getattr(TestOutbox.TestMailer, "__test__", True) is False


def test_a_test_component_nested_in_a_class_holds_for_that_class_only() -> None:
    class TestOutbox:
        @test_component(replaces=Mailer)
        class OutboxMailer(Mailer):
            pass

    assert replacing_components() == {}
    assert nested_test_components([TestOutbox]) == {Mailer: TestOutbox.OutboxMailer}


def test_a_nested_class_sees_the_test_components_of_the_classes_around_it_and_its_own_win() -> None:
    class TestOuter:
        @test_component(replaces=Mailer)
        class OuterMailer(Mailer):
            pass

        @test_component(replaces=Printer)
        class OuterPrinter(Printer):
            pass

        class TestInner:
            @test_component(replaces=Mailer)
            class InnerMailer(Mailer):
                pass

    found = nested_test_components([TestOuter, TestOuter.TestInner])

    assert found == {Mailer: TestOuter.TestInner.InnerMailer, Printer: TestOuter.OuterPrinter}


def test_a_test_class_has_the_nested_test_components_of_its_bases() -> None:
    class TestBase:
        @test_component(replaces=Mailer)
        class BaseMailer(Mailer):
            pass

    class TestDerived(TestBase):
        pass

    assert nested_test_components([TestDerived]) == {Mailer: TestBase.BaseMailer}


def test_a_test_component_merely_named_in_a_class_is_not_nested_in_it() -> None:
    @test_component(replaces=Mailer)
    class OutboxMailer(Mailer):
        pass

    class TestOutbox:
        mailer = OutboxMailer

        class LoudMailer(OutboxMailer):
            pass

    assert nested_test_components([TestOutbox]) == {}


def test_a_test_without_classes_or_nested_test_components_has_none() -> None:
    class TestWithoutDoubles:
        pass

    assert nested_test_components([]) == {}
    assert nested_test_components([TestWithoutDoubles], mocked={Mailer}) == {}


def test_two_nested_test_components_for_one_component_stop_the_start() -> None:
    class TestOutbox:
        @test_component(replaces=Mailer)
        class OutboxMailer(Mailer):
            pass

        @test_component(replaces=Mailer)
        class SilentMailer(Mailer):
            pass

    with pytest.raises(InvalidTestComponentError, match=r"OutboxMailer and \S+SilentMailer both replace Mailer"):
        nested_test_components([TestOutbox])


def test_a_nested_test_component_beside_a_mock_of_its_component_stops_the_start() -> None:
    class TestOutbox:
        @test_component(replaces=Mailer)
        class OutboxMailer(Mailer):
            pass

    with pytest.raises(InvalidTestComponentError, match=r"OutboxMailer and a MockComponent both replace Mailer"):
        nested_test_components([TestOutbox], mocked={Mailer})


def test_a_mock_of_an_inner_class_wins_over_a_test_component_around_it() -> None:
    class TestOuter:
        @test_component(replaces=Mailer)
        class OuterMailer(Mailer):
            pass

        class TestInner:
            pass

    found = nested_test_components([TestOuter, TestOuter.TestInner], mocked={Mailer})

    assert found == {Mailer: TestOuter.OuterMailer}
