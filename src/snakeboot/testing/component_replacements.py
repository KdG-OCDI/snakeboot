import inspect
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

_REPLACEMENTS: dict[Any, type] = {}


class InvalidTestComponentError(TypeError):
    """Raised when two test components replace one component: which of them a test gets would be a guess."""


def test_component[C: type](*, replaces: Any) -> Callable[[C], C]:
    """Makes a class of the tests replace the component of type `replaces` in every `@application_test`.

    Like a class with Spring Boot's `@TestComponent` and `@Primary`, imported into every test: snakeboot finds it in
    the project's source, builds it anew for every test (without arguments) and hands it to whatever needs a
    `replaces`. A test reaches it by its own type too, to drive it:

        @test_component(replaces=ClockPort)
        class FixedClock(ClockPort):
            def __init__(self, now: datetime = NOW) -> None: ...
            def advance(self, duration: timedelta) -> None: ...

        @application_test
        def test_a_bid_after_the_closing_time_is_refused(clock: Autowired[FixedClock]) -> None: ...

    A test component replaces a component the application has; for an application without one it does nothing. A
    `MockComponent` of the same type wins for its test.
    """

    def register(component: C) -> C:
        earlier = _REPLACEMENTS.get(replaces)
        if earlier is not None and _source_of(earlier) != _source_of(component):
            name = getattr(replaces, "__qualname__", repr(replaces))
            raise InvalidTestComponentError(
                f"{earlier.__module__}.{earlier.__qualname__} and {component.__module__}.{component.__qualname__} "
                f"both replace {name}: keep one test component per component, and give a test that needs another a "
                "MockComponent."
            )
        _REPLACEMENTS[replaces] = component
        return component

    return register


test_component.__test__ = False  # type: ignore[attr-defined]  # pytest: a function named test_... that is no test


def replacing_components() -> Mapping[Any, type]:
    """Returns every test component imported so far, by the type of the component it replaces."""
    return MappingProxyType(_REPLACEMENTS)


def _source_of(component: type) -> str:
    # One class imported twice, under two module names, is still one test component.
    try:
        return f"{inspect.getfile(component)}:{component.__qualname__}"
    except TypeError:
        return f"{component.__module__}:{component.__qualname__}"
