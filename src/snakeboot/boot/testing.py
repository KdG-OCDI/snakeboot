from collections.abc import Callable, Mapping
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self, cast, override
from unittest.mock import Mock

from snakeboot.application import ApplicationContext
from snakeboot.boot.entry_points import CONDITIONAL_MODULES, web_api
from snakeboot.cache import Cache, InMemoryCache
from snakeboot.configuration import CacheProperties, Configuration, DatabaseProperties, ServerProperties
from snakeboot.events import SyncTaskExecutor, TaskExecutor
from snakeboot.lifecycle.application_lifecycle import ApplicationLifecycle
from snakeboot.lifecycle.lifecycle_asgi_application import LifecycleAsgiApplication
from snakeboot.rest import BearerAuthentication
from snakeboot.security import Principal
from snakeboot.testing.signed_in_tokens import signed_in_principal

if TYPE_CHECKING:
    from httpx2 import Response
    from starlette.testclient import TestClient

type RestClient = TestClient
"""The client of `TestApplication.client()`: `get`, `post`, `put`, `patch` and `delete` return a `RestResponse`."""

type RestResponse = Response
"""An answer of the REST API to a test: `status_code`, `headers`, `json()` and `text`."""


class TestApplication:
    """A started application for a test, like Spring Boot's `@SpringBootTest` with `@AutoConfigureTestDatabase`.

        with TestApplication.start(TictactoeApplication, overrides={GamePlatformPort: FakePlatform()}) as app:
            client = app.client()                                  # calls the REST API, like TestRestTemplate
            assert client.get("/api/tictactoe/games/42").status_code == 404
            assert app.get(GameRecords).count() == 0               # any component of the container

    The application starts as it does for real, from its application.toml and the active profile, with these
    differences: `overrides` replace components with doubles; with `[database]` the database is a fresh one in
    memory whose tables come from the entities, as Spring Boot's tests create the schema from JPA's metamodel; with
    `[cache]` the cache is an `InMemoryCache`; the `@application_module_listener` methods run on the caller's thread,
    so what they did is there when the call that published returns; and the API accepts the tokens of
    `signed_in_as` next to its own. A test of the SQL migrations themselves runs `migrate` against a real database.

    `snakeboot.testing.application_test` starts it for a test and injects what the test asks for.
    """

    __test__ = False  # pytest: a class named Test... that is no test class

    def __init__(self, context: ApplicationContext, replacements: Mapping[Any, object] | None = None) -> None:
        self._context = context
        self._replacements = dict(replacements or {})

    @classmethod
    def start(
        cls,
        application: type,
        overrides: Mapping[Any, object] | None = None,
        *,
        profile: str | None = None,
        properties: Mapping[str, object] | None = None,
        test_components: Mapping[Any, object] | None = None,
    ) -> Self:
        """Starts `application` with `overrides` and, when it has `[database]`, a database in memory.

        `profile` and `properties` win over the files and the environment, like `@ActiveProfiles` and
        `@SpringBootTest(properties = ...)`: `properties={"scheduling.auto_startup": False}`. `test_components`
        replace the components the application has, unless `overrides` replaces the same; for an application without
        one of them, it does nothing.
        """
        context = ApplicationContext.of(application, CONDITIONAL_MODULES, profile=profile, properties=properties)
        explicit = dict(overrides or {})
        replacements = {TaskExecutor: SyncTaskExecutor(), **_in_memory_services(context.configuration, explicit)}
        replacements |= explicit
        context.refresh(replacements)
        replacements |= _replaced_where_present(context, test_components or {}, replacements)
        if DatabaseProperties in context.configuration.sections:
            _create_tables(context)
        started = cls(context, replacements)
        started._accept_signed_in_tokens()
        return started

    @property
    def configuration(self) -> Configuration:
        """What the application read: its sections, by class."""
        return self._context.configuration

    def get[T](self, component_type: Callable[..., T]) -> T:
        """Returns the component of `component_type`, a double that replaced it included.

        A double is also found by its own type: `get(FixedClock)` returns the `FixedClock` that replaced the clock.
        """
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
        api = web_api(self._context)
        context = self._context

        async def lifecycle() -> ApplicationLifecycle:
            return context.get(ApplicationLifecycle)

        return TestClient(LifecycleAsgiApplication(api, lifecycle=lifecycle), base_url=_base_url_of(server))

    def close(self) -> None:
        """Closes the container and what it holds."""
        self._context.close()

    def __enter__(self) -> Self:
        """Returns the started application, which the end of the `with` block closes."""
        return self

    def __exit__(
        self, error_type: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None
    ) -> None:
        """Closes the application."""
        self.close()

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


def _in_memory_services(configuration: Configuration, overrides: Mapping[Any, object]) -> dict[Any, object]:
    services: dict[Any, object] = {}
    if DatabaseProperties in configuration.sections:
        services |= _in_memory_database(overrides)
    if CacheProperties in configuration.sections and Cache not in overrides:
        services[Cache] = InMemoryCache()
    return services


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


def _in_memory_database(replacements: Mapping[Any, object]) -> dict[Any, object]:
    from snakeboot.sqlalchemy_data import Database  # noqa: PLC0415  # reason: only an application with a database
    from snakeboot.sqlalchemy_data.testing import in_memory_database  # noqa: PLC0415  # reason: as above

    return {} if Database in replacements else {Database: in_memory_database()}


def _create_tables(context: ApplicationContext) -> None:
    from snakeboot.sqlalchemy_data import Database  # noqa: PLC0415  # reason: only an application with a database
    from snakeboot.sqlalchemy_data.entity_mapping import EntityMapping  # noqa: PLC0415  # reason: as above

    mapping = context.get(EntityMapping)
    mapping.metadata.create_all(context.get(Database).engine, tables=mapping.tables)


def _base_url_of(server: ServerProperties) -> str:
    host = next((host for host in server.allowed_hosts if host != "*"), "testserver")
    return f"http://{host.replace('*.', 'test.')}"
