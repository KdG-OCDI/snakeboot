import inspect
from collections.abc import Callable, Collection, Mapping, Sequence
from types import MappingProxyType
from typing import Any, Final

_REPLACEMENTS: dict[Any, type] = {}
_REPLACES: Final = "__snakeboot_replaces__"


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

    Nested in a test class, like a static nested `@TestConfiguration`, it holds for that class only: for its tests and
    those of the classes nested in it, where it wins over a test component of the project for the same component.

        @application_test
        class TestWithARepositoryThatLosesTheUpdate:
            @test_component(replaces=AuctionRepositoryPort)
            class RepositoryThatLosesTheUpdate: ...

    A test component replaces a component the application has; for an application without one it does nothing. A
    `MockComponent` of the same type wins for its test; beside a test component nested in the test's own class, it
    stops the test.
    """

    def register(component: C) -> C:
        setattr(component, _REPLACES, replaces)
        component.__test__ = False  # type: ignore[attr-defined]  # pytest: a nested class named Test... is no test
        if not _nested_in_a_class(component):
            _register_for_every_test(component, replaces)
        return component

    return register


test_component.__test__ = False  # type: ignore[attr-defined]  # pytest: a function named test_... that is no test


def replacing_components() -> Mapping[Any, type]:
    """Returns every test component imported so far, by the type of the component it replaces; not the nested ones."""
    return MappingProxyType(_REPLACEMENTS)


def nested_test_components(test_classes: Sequence[type], mocked: Collection[Any] = ()) -> dict[Any, type]:
    """Returns the test components nested in `test_classes`, by the type of the component they replace.

    `test_classes` are the class of a test and the classes it is nested in, the outermost first: a pytest class nested
    in another sees the test components of the classes around it, as a JUnit `@Nested` class inherits their
    configuration, and for one component the innermost class's wins. A class has those of its bases too. `mocked` are
    the types of the test's `MockComponent`s: one that a test component nested in the test's own class replaces too
    stops the test, since which of the two it gets would be a guess.
    """
    per_class = [_nested_in_class_or_bases(test_class) for test_class in test_classes]
    if per_class:
        _refuse_mocks_of(per_class[-1], mocked)
    found: dict[Any, type] = {}
    for nested in per_class:
        found |= nested
    return found


def _register_for_every_test(component: type, replaces: Any) -> None:
    earlier = _REPLACEMENTS.get(replaces)
    if earlier is not None and _source_of(earlier) != _source_of(component):
        raise InvalidTestComponentError(
            f"{earlier.__module__}.{earlier.__qualname__} and {component.__module__}.{component.__qualname__} "
            f"both replace {_name_of(replaces)}: keep one test component per component, and give a test that needs "
            "another a MockComponent."
        )
    _REPLACEMENTS[replaces] = component


def _nested_in_a_class(component: type) -> bool:
    # The compiler names where a class stands: `Outer.Inner` in a class, `test.<locals>.Inner` in a function.
    enclosing = component.__qualname__.rpartition(".")[0]
    return bool(enclosing) and not enclosing.endswith("<locals>")


def _nested_in_class_or_bases(test_class: type) -> dict[Any, type]:
    found: dict[Any, type] = {}
    for declaring_class in reversed(test_class.__mro__):
        found |= _nested_right_in(declaring_class)
    return found


def _nested_right_in(declaring_class: type) -> dict[Any, type]:
    found: dict[Any, type] = {}
    for member in vars(declaring_class).values():
        if not _is_test_component_nested_in(member, declaring_class):
            continue
        replaces = vars(member)[_REPLACES]
        if replaces in found:
            raise InvalidTestComponentError(
                f"{found[replaces].__qualname__} and {member.__qualname__} both replace {_name_of(replaces)}: keep "
                "one test component per component in a test class."
            )
        found[replaces] = member
    return found


def _is_test_component_nested_in(member: object, declaring_class: type) -> bool:
    # A test component merely named in the class body, or a subclass of one, is not one of its own.
    return (
        isinstance(member, type)
        and _REPLACES in vars(member)
        and member.__qualname__ == f"{declaring_class.__qualname__}.{member.__name__}"
    )


def _refuse_mocks_of(nested: Mapping[Any, type], mocked: Collection[Any]) -> None:
    for replaces, component in nested.items():
        if replaces in mocked:
            raise InvalidTestComponentError(
                f"{component.__qualname__} and a MockComponent both replace {_name_of(replaces)} in one test class: "
                "keep one of them."
            )


def _name_of(replaces: Any) -> str:
    return getattr(replaces, "__qualname__", repr(replaces))


def _source_of(component: type) -> str:
    # One class imported twice, under two module names, is still one test component.
    try:
        return f"{inspect.getfile(component)}:{component.__qualname__}"
    except TypeError:
        return f"{component.__module__}:{component.__qualname__}"
