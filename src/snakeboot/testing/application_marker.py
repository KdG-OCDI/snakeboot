import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import wraps
from types import MappingProxyType
from typing import Any, Final, cast, get_type_hints, overload

from snakeboot.testing.environment import PostgreSQLContainer, TestEnvironment
from snakeboot.testing.injection import InjectionPoint, injection_points
from snakeboot.testing.slices import ApplicationSlice, ModuleSlice, WebSlice

APPLICATION_TEST_FIXTURE: Final = "snakeboot_application_test"
"""The pytest fixture that starts the application of an `@application_test`: snakeboot's pytest plugin provides it."""

_MARKER: Final = "__snakeboot_application_test__"
_PARAMETERS: Final = "__snakeboot_injected_parameters__"


@dataclass(frozen=True, slots=True)
class ApplicationTest:
    """How an `@application_test` starts its application: which one, in which `TestEnvironment`, and how much of it.

    Without `application`, the test starts the one class with `@application_root` in the project's source, as
    Spring Boot finds the `@SpringBootConfiguration`. Without `only`, it starts the whole application; with a slice,
    only that part (`@web_test`, `@application_module_test`).
    """

    application: type | None = None
    environment: TestEnvironment = field(default_factory=TestEnvironment)
    only: ApplicationSlice | None = None

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
    *,
    application: type | None = None,
    profile: str | None = None,
    properties: Mapping[str, object] | None = None,
    database: PostgreSQLContainer | None = None,
) -> ApplicationTest: ...


def application_test(
    test: object = None,
    /,
    *,
    application: type | None = None,
    profile: str | None = None,
    properties: Mapping[str, object] | None = None,
    database: PostgreSQLContainer | None = None,
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
    `@application_test(database=PostgreSQLContainer())` runs the test on PostgreSQL, built by the application's own
    migrations, instead of SQLite in memory.
    """
    properties = MappingProxyType(dict(properties or {}))
    marker = ApplicationTest(application, TestEnvironment(profile, properties, database))
    return marker if test is None else marker(test)


@overload
def web_test[T](test: T, /) -> T: ...


@overload
def web_test(
    *, application: type | None = None, profile: str | None = None, properties: Mapping[str, object] | None = None
) -> ApplicationTest: ...


def web_test(
    test: object = None,
    /,
    *,
    application: type | None = None,
    profile: str | None = None,
    properties: Mapping[str, object] | None = None,
) -> object:
    """A test of the REST layer alone, like `@WebMvcTest`: controllers, advices, the authentication and sections.

        @web_test
        class TestAuctionRestController:
            client: Autowired[RestClient]
            place_bid: MockComponent[PlaceBidUseCase]     # @MockitoBean: the use cases are left out

            def test_a_bid_that_is_too_low_answers_409(self) -> None:
                when(self.place_bid.execute).then_raise(BidTooLowError("..."))
                ...

    Every other module of the application is left out (`WebSlice`), so a controller's use cases and ports are given
    as a `MockComponent`, as is a repository that an advice or the authentication needs; one that is missing stops the
    test and names it. The calls carry `signed_in_as`, and the controllers' own `@roles_allowed` and advices answer,
    as in the whole application. Like `@WebMvcTest`, which configures no datasource, it runs no migrations: a
    migration in PostgreSQL's own SQL, which SQLite refuses, does not stop it.
    """
    properties = MappingProxyType(dict(properties or {}))
    marker = ApplicationTest(application, TestEnvironment(profile, properties), only=WebSlice())
    return marker if test is None else marker(test)


def application_module_test(
    *packages: str,
    application: type | None = None,
    profile: str | None = None,
    properties: Mapping[str, object] | None = None,
    database: PostgreSQLContainer | None = None,
) -> ApplicationTest:
    """A test of bounded contexts on their own, like Spring Modulith's `@ApplicationModuleTest`.

        @application_module_test("auction_house.invoicing")
        class TestInvoicing:
            events: Autowired[ApplicationEventPublisher]
            invoices: Autowired[InvoiceRepositoryPort]

    Only the modules of `packages`, of the application's package itself and those that declare a section join the
    application (`ModuleSlice`): the other contexts are left out, so whatever these use of them is given as a
    `MockComponent`, and a dependency nobody gave stops the test and names it. Every migration of the application
    runs, as `migrate` runs them; `database=PostgreSQLContainer()` runs them on PostgreSQL instead of SQLite in memory.
    """
    if not packages:
        raise TypeError("@application_module_test names the packages of the contexts it starts.")
    properties = MappingProxyType(dict(properties or {}))
    environment = TestEnvironment(profile, properties, database)
    return ApplicationTest(application, environment, only=ModuleSlice(packages))


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
