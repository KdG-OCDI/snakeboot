from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module
from types import ModuleType, TracebackType
from typing import TYPE_CHECKING, Any, Final, Self, cast, override
from unittest.mock import Mock

import wireup
from wireup.errors import WireupError

from snakeboot.application import ApplicationContext
from snakeboot.boot.entry_points import CONDITIONAL_MODULES, web_api
from snakeboot.boot.local_server import LOOPBACK, LocalServer, ServerClient
from snakeboot.cache import Cache, InMemoryCache
from snakeboot.component_scan import ComponentScan, application_package, narrowed_application
from snakeboot.configuration import (
    CacheProperties,
    Configuration,
    DatabaseProperties,
    OAuth2Properties,
    RabbitProperties,
    ServerProperties,
    sections_declared_in,
)
from snakeboot.events import ApplicationEventListener, SyncTaskExecutor, TaskExecutor, event_listener
from snakeboot.lifecycle.application_lifecycle import ApplicationLifecycle
from snakeboot.lifecycle.lifecycle_asgi_application import LifecycleAsgiApplication
from snakeboot.rest import BearerAuthentication
from snakeboot.rest.bearer_authentication import AUTHENTICATION_MARKER_ATTRIBUTE
from snakeboot.rest.rest_controller_mappings import ADVICE_MARKER_ATTRIBUTE, CONTROLLER_MAPPING_ATTRIBUTE
from snakeboot.security import Principal
from snakeboot.testing.environment import TestEnvironment
from snakeboot.testing.published_events import PublishedEvents
from snakeboot.testing.signed_in_tokens import signed_in_principal
from snakeboot.testing.slices import ApplicationSlice, ModuleSlice, WebSlice

if TYPE_CHECKING:
    from httpx2 import Response
    from starlette.testclient import TestClient

__all__ = ["SPY", "LocalServer", "RestClient", "RestResponse", "ServerClient", "TestApplication"]

type RestClient = TestClient
"""The client of `TestApplication.client()`: `get`, `post`, `put`, `patch` and `delete` return a `RestResponse`."""

type RestResponse = Response
"""An answer of the REST API to a test: `status_code`, `headers`, `json()` and `text`."""


class SpyMarker:
    """The type of `SPY`, which asks `TestApplication.start` for a spy around a component instead of a double."""

    @override
    def __repr__(self) -> str:
        return "SPY"


SPY: Final = SpyMarker()
"""The double of a type in `TestApplication.start(overrides=...)` that wraps the application's own component in a spy,
like `@MockitoSpyBean`: `overrides={PaymentPort: SPY}`, then `verify(app.get(PaymentPort).charge)`.

The spy replaces the component before anything that depends on it is built, the event listeners included, so it
records their calls too. A `SpyComponent[T]` of an `@application_test` passes it.
"""


class TestApplication:
    """A started application for a test, like Spring Boot's `@SpringBootTest` with `@AutoConfigureTestDatabase`.

        with TestApplication.start(TictactoeApplication, overrides={GamePlatformPort: FakePlatform()}) as app:
            client = app.client()                                  # calls the REST API, like TestRestTemplate
            assert client.get("/api/tictactoe/games/42").status_code == 404
            assert app.get(GameRecords).count() == 0               # any component of the container

    The application starts as it does for real, from its application.toml and the active profile, with these
    differences: `overrides` replace components with doubles, or wrap them in a spy (`SPY`); with `[database]` the
    database is a fresh SQLite in memory that the application's migrations built and that was checked against the
    entities, as Spring Boot's tests run Flyway on H2 with `ddl-auto=validate` (without migrations, or in a `WebSlice`,
    which runs none, the tables of the entities), or a copy of a PostgreSQL that the migrations built
    (`TestEnvironment.database`); with `[cache]` the cache is an `InMemoryCache`;
    with `[rabbitmq]` the `RabbitTemplate` hands its messages to the application's own `@rabbit_listener` methods,
    without a broker (`InProcessRabbitTemplate`); the `@application_module_listener` methods run on the caller's
    thread, so what they did is there when the call that published returns; every event is kept in
    `published_events`; the API accepts the tokens of `signed_in_as` next to its own, and with `[oauth2]` the tokens
    its `AuthorizationServer` signs (`snakeboot.oauth2.testing`). `local_server()` serves it over HTTP.

    `snakeboot.testing.application_test` starts it for a test and injects what the test asks for.
    """

    __test__ = False  # pytest: a class named Test... that is no test class

    def __init__(
        self,
        context: ApplicationContext,
        replacements: Mapping[Any, object] | None = None,
        *,
        extras: Mapping[type, object] | None = None,
        owned: Sequence[Any] = (),
    ) -> None:
        self._context = context
        self._replacements = dict(replacements or {})
        self._extras: dict[type, object] = {PublishedEvents: PublishedEvents(), **(extras or {})}
        self._owned = list(owned)
        self._server: LocalServer | None = None

    @classmethod
    def start(
        cls,
        application: type,
        overrides: Mapping[Any, object] | None = None,
        *,
        environment: TestEnvironment | None = None,
        test_components: Mapping[Any, object] | None = None,
        only: ApplicationSlice | None = None,
    ) -> Self:
        """Starts `application` with `overrides`, in `environment`: by default without a profile and in memory.

        `test_components` replace the components the application has, unless `overrides` replaces the same; for an
        application without one of them, it does nothing. A type that `overrides` maps to `SPY` gets a spy around its
        component, the test component included, before the listeners are built. `only` starts part of the
        application, a `WebSlice` or a `ModuleSlice`: then `overrides` join the container, standing in for what the
        slice leaves out, and a dependency nobody gave stops the start with its name. A `ModuleSlice` runs every
        migration of the application; a `WebSlice` runs none, on SQLite in memory whatever `environment.database` says.
        """
        environment = environment or TestEnvironment()
        context = ApplicationContext.of(
            _narrowed(application, only),
            CONDITIONAL_MODULES,
            profile=environment.profile,
            properties=environment.properties,
        )
        overrides = overrides or {}
        explicit = {component_type: double for component_type, double in overrides.items() if double is not SPY}
        spied = tuple(component_type for component_type, double in overrides.items() if double is SPY)
        services = _test_services(context, environment, explicit, migrated=_migrated(application, only))
        doubles = _Doubles(services, explicit, joining=only is not None, spied=spied)
        try:
            return cls._started(context, doubles=doubles, test_components=test_components)
        except WireupError as error:
            _close(doubles.services.values())
            if only is None:
                raise
            raise LookupError(f"{error}\n{_SLICE_HINT}") from error
        except BaseException:
            _close(doubles.services.values())
            raise

    @property
    def configuration(self) -> Configuration:
        """What the application read: its sections, by class."""
        return self._context.configuration

    @property
    def published_events(self) -> PublishedEvents:
        """Every event the application published since it started, like Spring's `ApplicationEvents`."""
        return cast("PublishedEvents", self._extras[PublishedEvents])

    def get[T](self, component_type: Callable[..., T]) -> T:
        """Returns the component of `component_type`, a double that replaced it included.

        A double is also found by its own type: `get(FixedClock)` returns the `FixedClock` that replaced the clock.
        `get(PublishedEvents)` returns `published_events`, `get(LocalServer)` the `local_server()`, and with `[oauth2]`
        `get(AuthorizationServer)` the authorization server of the test.
        """
        if component_type is LocalServer:
            return cast("T", self.local_server())
        if isinstance(component_type, type) and component_type in self._extras:
            return cast("T", self._extras[component_type])
        try:
            return self._context.get(component_type)
        except LookupError:
            double = self._double_of(component_type)
            if double is None:
                raise
            return cast("T", double)

    def spy[T](self, component_type: Callable[..., T]) -> T:
        """Replaces the component of `component_type` with a spy around it, like `@MockitoSpyBean`, and returns it.

        The spy does what the component does and records its calls, for `verify(...)`; `when(...)` changes what a
        method answers. Components built before keep the component itself, so a test spies before its first call.
        The event listeners are built while the application starts, so they keep it too: to record what they call,
        `start` the application with `overrides={component_type: SPY}`, as a `SpyComponent` does.
        """
        component = self.get(component_type)
        spy = Mock(spec=component, wraps=component)
        self._context.replace_component(component_type, spy)
        self._replacements[component_type] = spy
        return cast("T", spy)

    def client(self) -> RestClient:
        """Returns a client of the REST API that calls the application in this process, like `TestRestTemplate`.

        The calls go to the first of `[server] allowed_hosts`. Used as a context manager (`with app.client() as
        client:`), the lifecycle starts and stops around it, as the server's would.
        """
        from starlette.testclient import TestClient  # noqa: PLC0415  # reason: only a test of the API needs it

        server = self._context.configuration.get(ServerProperties)
        return TestClient(self._asgi_application(), base_url=_base_url_of(server))

    def local_server(self) -> LocalServer:
        """Serves the application over HTTP on a free port, the first time it is asked, and returns the server.

        Like `@SpringBootTest(webEnvironment = RANDOM_PORT)`: `local_server().url` is where it listens, and its
        `client()` calls it over the network. The lifecycle runs while it serves; closing the application stops it.
        """
        if self._server is None:
            self._server = LocalServer.start(self._asgi_application(also_allowed_hosts=(LOOPBACK, "localhost")))
        return self._server

    def close(self) -> None:
        """Stops its server, closes the container and what it holds, and the database of the test."""
        try:
            if self._server is not None:
                self._server.stop()
        finally:
            try:
                self._context.close()
            finally:
                _close(self._owned)

    def __enter__(self) -> Self:
        """Returns the started application, which the end of the `with` block closes."""
        return self

    def __exit__(
        self, error_type: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None
    ) -> None:
        """Closes the application."""
        self.close()

    @classmethod
    def _started(
        cls,
        context: ApplicationContext,
        *,
        doubles: "_Doubles",
        test_components: Mapping[Any, object] | None,
    ) -> Self:
        extras, additions = _test_extras(context)
        replacements = {**doubles.services, **doubles.explicit}
        # What the test made for itself, it closes: the database of a test drops its PostgreSQL copy.
        started = cls(context, replacements, extras=extras, owned=list(doubles.services.values()))
        context.refresh(
            doubles.replacing(),
            additions=[*additions, *doubles.joining_the_container()],
            prepare=lambda _: started._prepare(test_components or {}, doubles.spied),
        )
        return started

    def _prepare(self, test_components: Mapping[Any, object], spied: Sequence[Any]) -> None:
        # Before the listeners are built, so that they receive the test components and the spies too.
        self._replacements |= _replaced_where_present(self._context, test_components, self._replacements)
        self._accept_signed_in_tokens()
        for component_type in spied:
            self.spy(component_type)

    def _asgi_application(self, *, also_allowed_hosts: tuple[str, ...] = ()) -> LifecycleAsgiApplication:
        api = web_api(self._context, also_allowed_hosts=also_allowed_hosts)
        context = self._context

        async def lifecycle() -> ApplicationLifecycle:
            return context.get(ApplicationLifecycle)

        return LifecycleAsgiApplication(api, lifecycle=lifecycle)

    def _double_of(self, component_type: object) -> object | None:
        if not isinstance(component_type, type):
            return None
        try:
            found = [double for double in self._replacements.values() if isinstance(double, component_type)]
        except TypeError:  # a Protocol that is not runtime-checkable
            return None
        return found[0] if len(found) == 1 else None

    def _accept_signed_in_tokens(self) -> None:
        # A test that replaced the authentication itself decides what it accepts.
        if BearerAuthentication in self._replacements:
            return
        try:
            authentication = self._context.get(BearerAuthentication)
        except LookupError:  # an API without authentication
            return
        self._context.replace_component(BearerAuthentication, _SignedInTokens(authentication))


class _SignedInTokens(BearerAuthentication, component=False):
    """The application's own authentication, which in a test also accepts the tokens of `signed_in_as`."""

    def __init__(self, authentication: BearerAuthentication) -> None:
        self._authentication = authentication

    @override
    def authenticate(self, token: str) -> Principal | str | None:
        return signed_in_principal(token) or self._authentication.authenticate(token)


_SLICE_HINT: Final = (
    "A slice starts part of the application: what it leaves out, a test gives as a MockComponent; what it holds, a "
    "MockComponent cannot stand in for."
)


@dataclass(frozen=True, slots=True)
class _Doubles:
    """What a test puts in place of the application's own: its infrastructure, made here, its own doubles, and the
    types whose component it wraps in a spy."""

    services: Mapping[Any, object]
    explicit: Mapping[Any, object]
    joining: bool
    spied: tuple[Any, ...] = ()

    def replacing(self) -> dict[Any, object]:
        """What replaces a component of the container: in a slice, the test's doubles join it instead."""
        return dict(self.services) if self.joining else {**self.services, **self.explicit}

    def joining_the_container(self) -> list[object]:
        """The test's doubles as wireup's injectables, in a slice that lacks what they stand in for."""
        if not self.joining:
            return []
        return [_provider(component_type, double) for component_type, double in self.explicit.items()]


def _provider(component_type: Any, double: object) -> object:
    """A provider of `double` as the component of `component_type`, for wireup.

    `wireup.instance` would refuse a mock: `create_autospec` makes `isinstance` true, but the mock's own class is no
    subclass of the type. A provider announces the type by its return annotation instead.
    """

    def provide() -> object:
        return double

    provide.__annotations__ = {"return": component_type}
    provide.__name__ = provide.__qualname__ = f"provide_{getattr(component_type, '__name__', 'double')}"
    return wireup.injectable(provide)


class _PublishedEventsListener:
    """Hears every event the application publishes, at once, and keeps it in the test's `PublishedEvents`."""

    def __init__(self, events: PublishedEvents) -> None:
        self._events = events

    @event_listener(object)
    def record(self, event: object) -> None:
        """Keeps `event`."""
        self._events.record(event)


def _test_extras(context: ApplicationContext) -> tuple[dict[type, object], list[object]]:
    """What a test reaches besides the container: its `PublishedEvents`, and with `[oauth2]` an authorization server;
    and the injectables that connect them to the application."""
    events = PublishedEvents()
    extras: dict[type, object] = {PublishedEvents: events}
    additions = [_recording(events)]
    if OAuth2Properties in context.configuration.sections:
        issuer, signing_keys = _authorization_server(context.configuration.get(OAuth2Properties))
        extras[type(issuer)] = issuer
        additions.append(signing_keys)
    return extras, additions


def _authorization_server(properties: OAuth2Properties) -> tuple[object, object]:
    from snakeboot.oauth2 import JwtSigningKeys  # noqa: PLC0415  # reason: only an application with [oauth2]
    from snakeboot.oauth2.testing import AuthorizationServer  # noqa: PLC0415  # reason: as above

    issuer = AuthorizationServer(properties)
    keys = issuer.signing_keys()

    def provide_signing_keys() -> JwtSigningKeys | None:
        return keys

    return issuer, wireup.injectable(provide_signing_keys)


def _recording(events: PublishedEvents) -> object:
    listener = _PublishedEventsListener(events)
    return wireup.instance(listener, as_type=ApplicationEventListener, qualifier="snakeboot.testing.PublishedEvents")


def _test_services(
    context: ApplicationContext,
    environment: TestEnvironment,
    overrides: Mapping[Any, object],
    *,
    migrated: type | None,
) -> dict[Any, object]:
    """The executor, the database, the cache and the broker of a test, in place of the application's own."""
    sections = context.configuration.sections
    services: dict[Any, object] = {TaskExecutor: SyncTaskExecutor()}
    if DatabaseProperties in sections:
        services |= _test_database(context, environment, overrides, migrated=migrated)
    if CacheProperties in sections and Cache not in overrides:
        services[Cache] = InMemoryCache()
    if RabbitProperties in sections:
        services |= _in_process_rabbit(context, overrides)
    return services


def _migrated(application: type, only: ApplicationSlice | None) -> type | None:
    """The application whose migrations build the database of a test: the whole `application`, as `migrate` runs
    them, also for a `ModuleSlice`; none for a `WebSlice`, which, like `@WebMvcTest`, sets up no database of its own."""
    return None if isinstance(only, WebSlice) else application


def _test_database(
    context: ApplicationContext,
    environment: TestEnvironment,
    overrides: Mapping[Any, object],
    *,
    migrated: type | None,
) -> dict[Any, object]:
    """The database of a test, on the schema the migrations of the whole `migrated` application build, also when
    `context` starts a slice of it; the entities of `context` are what the schema is checked against.

    Without `migrated`, no migration runs, whatever the environment: the database is SQLite in memory with the tables
    of the entities of `context`, made from the entities as for an application without migrations. In a `WebSlice`
    those are snakeboot's own, of the event publication registry and the scheduler locks, which stay in every slice.
    """
    from snakeboot.data import ENTITY_ATTRIBUTE  # noqa: PLC0415  # reason: only an application with a database
    from snakeboot.sqlalchemy_data import Database  # noqa: PLC0415  # reason: as above
    from snakeboot.sqlalchemy_data.schema_migrations import migration_locations, migrations_in  # noqa: PLC0415  # reason: as above
    from snakeboot.sqlalchemy_data.testing import in_memory_database, postgresql_database  # noqa: PLC0415  # reason: as above

    if Database in overrides:
        return {}
    entity_types = context.classes_marked(ENTITY_ATTRIBUTE)
    if migrated is None:
        return {Database: in_memory_database(entity_types, migrations=())}
    sliced = context.application is not migrated
    every_entity = ComponentScan.of(migrated).classes_marked(ENTITY_ATTRIBUTE) if sliced else entity_types
    migrations = migrations_in(migration_locations(every_entity))
    if environment.database is None:
        return {Database: in_memory_database(entity_types, migrations=migrations)}
    return {Database: postgresql_database(environment.database.image, entity_types, migrations=migrations)}


def _in_process_rabbit(context: ApplicationContext, overrides: Mapping[Any, object]) -> dict[Any, object]:
    from snakeboot.rabbitmq import RabbitTemplate  # noqa: PLC0415  # reason: only an application with a broker
    from snakeboot.rabbitmq.in_process_rabbit_template import InProcessRabbitTemplate  # noqa: PLC0415  # reason: as above

    return {} if RabbitTemplate in overrides else {RabbitTemplate: InProcessRabbitTemplate(context)}


def _close(services: Iterable[object]) -> None:
    for service in services:
        close = getattr(service, "close", None)
        if callable(close):
            close()


def _replaced_where_present(
    context: ApplicationContext, components: Mapping[Any, object], replacements: Mapping[Any, object]
) -> dict[Any, object]:
    replaced: dict[Any, object] = {}
    for component_type, component in components.items():
        if component_type not in replacements:
            try:
                context.replace_component(component_type, component)
            except LookupError:  # the application has no such component
                continue
            replaced[component_type] = component
    return replaced


def _narrowed(application: type, only: ApplicationSlice | None) -> type:
    """`application` without the modules `only` leaves out; snakeboot's own modules always stay."""
    if only is None:
        return application
    scan = ComponentScan.of(application)
    package = application_package(application)
    excluded = [
        name
        for name in scan.module_names()
        if name not in scan.auto_configuration and not _holds(only, import_module(name), package)
    ]
    return narrowed_application(application, excluded)


def _holds(only: ApplicationSlice, module: ModuleType, application_package_name: str) -> bool:
    if sections_declared_in(module):  # the configuration reads every table of application.toml
        return True
    if isinstance(only, ModuleSlice):
        return only.holds(module.__name__) or module.__name__.rpartition(".")[0] == application_package_name
    return any(_is_web(candidate) for candidate in _classes_of(module))  # a WebSlice


def _classes_of(module: ModuleType) -> list[type]:
    return [c for c in vars(module).values() if isinstance(c, type) and c.__module__ == module.__name__]


def _is_web(candidate: type) -> bool:
    markers = (CONTROLLER_MAPPING_ATTRIBUTE, ADVICE_MARKER_ATTRIBUTE, AUTHENTICATION_MARKER_ATTRIBUTE)
    return any(marker in vars(candidate) for marker in markers)


def _base_url_of(server: ServerProperties) -> str:
    host = next((host for host in server.allowed_hosts if host != "*"), "testserver")
    return f"http://{host.replace('*.', 'test.')}"
