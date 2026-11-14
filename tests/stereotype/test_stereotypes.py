"""A stereotype makes a class a component of the container, and says what the class is."""

from abc import ABC, abstractmethod
from typing import Annotated, Protocol, override

import pytest
import wireup

from snakeboot.component_scan import ComponentScan, application_root
from snakeboot.stereotype import (
    STEREOTYPE_ATTRIBUTE,
    InvalidComponentError,
    Qualifier,
    Stereotype,
    bean,
    component,
    repository,
    service,
    stereotype_of,
)


class ClockPort(ABC):
    @abstractmethod
    def now(self) -> int: ...


class Greeting(Protocol):
    def greet(self) -> str: ...


@component(as_type=ClockPort)
class FixedClock(ClockPort):
    @override
    def now(self) -> int:
        return 12


@repository
class Shelf:
    def __init__(self) -> None:
        self.books = ["Dune"]


@service
class CountBooksUseCase:
    def __init__(self, shelf: Shelf, clock: ClockPort) -> None:
        self._shelf = shelf
        self.clock = clock

    def execute(self) -> int:
        return len(self._shelf.books)


@component(as_type=Greeting)
class Friendly:
    def greet(self) -> str:
        return "Welcome"


@bean(qualifier="short")
def short_names() -> list[str]:
    return ["Ann"]


@bean(qualifier="long")
def long_names() -> list[str]:
    return ["Annabella"]


@component
class Register:
    def __init__(self, names: Annotated[list[str], Qualifier("long")]) -> None:
        self.names = names


@application_root
class StereotypedApplication: ...


def container() -> wireup.SyncContainer:
    return wireup.create_sync_container(
        injectables=[FixedClock, Shelf, CountBooksUseCase, Friendly, short_names, long_names, Register]
    )


def test_a_stereotyped_class_is_built_once_with_its_dependencies_by_type() -> None:
    built = container()

    use_case = built.get(CountBooksUseCase)

    assert use_case.execute() == 1
    assert use_case is built.get(CountBooksUseCase)
    assert isinstance(use_case.clock, FixedClock)


def test_as_type_is_the_port_others_ask_for() -> None:
    built = container()

    assert built.get(ClockPort).now() == 12
    assert built.get(Greeting).greet() == "Welcome"


def test_a_qualifier_tells_two_components_of_one_type_apart() -> None:
    assert container().get(Register).names == ["Annabella"]


@pytest.mark.parametrize(
    ("declared", "stereotype"),
    [(FixedClock, Stereotype.COMPONENT), (CountBooksUseCase, Stereotype.SERVICE), (Shelf, Stereotype.REPOSITORY)],
    ids=lambda value: getattr(value, "__name__", str(value)),
)
def test_the_class_remembers_its_stereotype(declared: type, stereotype: Stereotype) -> None:
    assert stereotype_of(declared) is stereotype


def test_a_subclass_does_not_inherit_the_stereotype() -> None:
    class Later(Shelf): ...

    assert stereotype_of(Later) is None
    assert stereotype_of(ClockPort) is None


def test_the_component_scan_finds_the_stereotyped_classes() -> None:
    found = ComponentScan.of(StereotypedApplication).classes_marked(STEREOTYPE_ATTRIBUTE)

    assert {Shelf, CountBooksUseCase, FixedClock, Friendly, Register} <= set(found)
    assert ClockPort not in found


def test_a_stereotype_on_a_function_is_refused_and_names_bean() -> None:
    def build() -> Shelf:
        return Shelf()

    with pytest.raises(InvalidComponentError, match=r"@service declares a class.*is a @bean"):
        service(build)  # type: ignore[call-overload]  # what the type checker refuses too


def test_a_bean_on_a_class_is_refused_and_names_component() -> None:
    with pytest.raises(InvalidComponentError, match=r"@bean declares a function.*is a @component"):
        bean(Shelf)


def test_a_class_that_does_not_extend_the_port_it_names_is_refused() -> None:
    class Sundial:
        def now(self) -> int:
            return 12

    with pytest.raises(InvalidComponentError, match="Sundial is declared as_type=ClockPort, which it does not extend"):
        component(as_type=ClockPort)(Sundial)
