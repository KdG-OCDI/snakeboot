import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import wraps
from types import MappingProxyType
from typing import Any, Final, cast, get_type_hints, overload

from snakeboot.testing.injection import InjectionPoint, injection_points

APPLICATION_TEST_FIXTURE: Final = "snakeboot_application_test"
"""The pytest fixture that starts the application of an `@application_test`: snakeboot's pytest plugin provides it."""

_MARKER: Final = "__snakeboot_application_test__"
_PARAMETERS: Final = "__snakeboot_injected_parameters__"


@dataclass(frozen=True, slots=True)
class ApplicationTest:
    """How an `@application_test` starts its application: which one, in which profile, with which properties.

    Without `application`, the test starts the one class with `@application_root` in the project's source, as
    Spring Boot finds the `@SpringBootConfiguration`.
    """

    application: type | None = None
    profile: str | None = None
    properties: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))

    def __call__[T](self, test: T) -> T:
        """Marks a test function, or every test of a test class."""
        if isinstance(test, type):
            return cast("T", _marked_class(test, self))
        if inspect.isfunction(test):
            return cast("T", _marked(_with_injected_parameters(test), self))
        raise TypeError(f"@application_test marks a test function or a test class, not {test!r}.")


@overload
def application_test[T](test: T, /) -> T: ...


@overload
def application_test(
    *, application: type | None = None, profile: str | None = None, properties: Mapping[str, object] | None = None
) -> ApplicationTest: ...


def application_test(
    test: object = None,
    /,
    *,
    application: type | None = None,
    profile: str | None = None,
    properties: Mapping[str, object] | None = None,
) -> object:
    """A test of the whole application, like `@SpringBootTest`: snakeboot starts it anew for every test it marks.

        @application_test
        class TestClosing:
            client: Autowired[RestClient]                 # @Autowired MockMvcTester client
            invoices: MockComponent[InvoiceRepository]   # @MockitoBean

            def test_a_closed_auction_takes_no_bids(self) -> None: ...

    On a function, its parameters are filled instead (`client: Autowired[RestClient]`); its other parameters stay
    pytest's fixtures. The application starts as with `TestApplication`, with every `@test_component` and the mocks
    and spies of the test. `@application_test(application=..., profile="test", properties={...})` names the
    application, like `@SpringBootTest(classes = ...)`, activates a profile, like `@ActiveProfiles`, and sets
    properties that win over every other source, like `@SpringBootTest(properties = ...)`.
    """
    marker = ApplicationTest(application, profile, MappingProxyType(dict(properties or {})))
    return marker if test is None else marker(test)


def application_test_of(test: object) -> ApplicationTest | None:
    """Returns the `@application_test` of a test function or a test class, or None."""
    marker = getattr(test, _MARKER, None)
    return marker if isinstance(marker, ApplicationTest) else None


def injected_fields_of(test_class: type) -> dict[str, InjectionPoint]:
    """Returns the annotated fields of a test class that its application fills, those of its bases included."""
    return injection_points(get_type_hints(test_class, include_extras=True))


def injected_parameters_of(test: Callable[..., object]) -> dict[str, InjectionPoint]:
    """Returns the parameters of a test that its application fills."""
    return dict(getattr(test, _PARAMETERS, {}))


def _marked[M](test: M, marker: ApplicationTest) -> M:
    setattr(test, _MARKER, marker)
    return test


def _marked_class(test_class: type, marker: ApplicationTest) -> type:
    # Every test of the class starts the application (snakeboot's plugin sees to it); only a method with
    # injected parameters needs a signature that hides them from pytest.
    for name, member in list(vars(test_class).items()):
        if inspect.isfunction(member) and _parameter_points(member):
            setattr(test_class, name, _with_injected_parameters(member))
    return _marked(test_class, marker)


def _parameter_points(test: Callable[..., object]) -> dict[str, InjectionPoint]:
    hints = get_type_hints(test, include_extras=True)
    return injection_points({name: hints[name] for name in inspect.signature(test).parameters if name in hints})


def _with_injected_parameters(test: Callable[..., object]) -> Callable[..., object]:
    """Wraps `test` in a function whose signature asks pytest for the fixture instead of the injected parameters."""
    points = _parameter_points(test)

    @wraps(test)
    def run(*args: Any, **kwargs: Any) -> object:
        injected: Mapping[str, object] = kwargs.pop(APPLICATION_TEST_FIXTURE)
        return test(*args, **kwargs, **injected)

    signature = inspect.signature(test)
    kept = [parameter for name, parameter in signature.parameters.items() if name not in points]
    fixture = inspect.Parameter(APPLICATION_TEST_FIXTURE, inspect.Parameter.KEYWORD_ONLY)
    before = [parameter for parameter in kept if parameter.kind is not inspect.Parameter.VAR_KEYWORD]
    after = [parameter for parameter in kept if parameter.kind is inspect.Parameter.VAR_KEYWORD]
    run.__signature__ = signature.replace(parameters=[*before, fixture, *after])  # type: ignore[attr-defined]
    setattr(run, _PARAMETERS, points)
    return run
