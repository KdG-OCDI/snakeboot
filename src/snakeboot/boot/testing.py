from collections.abc import Callable, Mapping
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self

from snakeboot.application import ApplicationContext
from snakeboot.boot.entry_points import CONDITIONAL_MODULES
from snakeboot.configuration import Configuration, DatabaseProperties, ServerProperties
from snakeboot.lifecycle.application_lifecycle import ApplicationLifecycle
from snakeboot.lifecycle.lifecycle_asgi_application import LifecycleAsgiApplication

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

    The application starts as it does for real, from its application.toml and the active profile, with two
    differences: `overrides` replace components with doubles, and with `[database]` the database is a fresh one in
    memory whose tables come from the entities, as Spring Boot's tests create the schema from JPA's metamodel. A test
    of the SQL migrations themselves runs `migrate` against a real database instead.
    """

    __test__ = False  # pytest: a class named Test... that is no test class

    def __init__(self, context: ApplicationContext) -> None:
        self._context = context

    @classmethod
    def start(cls, application: type, overrides: Mapping[Any, object] | None = None) -> Self:
        """Starts `application` with `overrides` and, when it has `[database]`, a database in memory."""
        context = ApplicationContext.of(application, CONDITIONAL_MODULES)
        replacements = dict(overrides or {})
        with_database = DatabaseProperties in context.configuration.sections
        if with_database:
            replacements.update(_in_memory_database(replacements))
        context.refresh(replacements)
        if with_database:
            _create_tables(context)
        return cls(context)

    @property
    def configuration(self) -> Configuration:
        """What the application read: its sections, by class."""
        return self._context.configuration

    def get[T](self, component_type: Callable[..., T]) -> T:
        """Returns the component of `component_type`, a double that replaced it included."""
        return self._context.get(component_type)

    def client(self) -> RestClient:
        """Returns a client of the REST API that calls the application in this process, like `TestRestTemplate`.

        The calls go to the first of `[server] allowed_hosts`. Used as a context manager (`with app.client() as
        client:`), the lifecycle starts and stops around it, as the server's would.
        """
        from starlette.testclient import TestClient  # noqa: PLC0415  # reason: only a test of the API needs it

        from snakeboot.fastapi_web import rest_api  # noqa: PLC0415  # reason: only a test of the API needs it

        server = self._context.configuration.get(ServerProperties)
        api = rest_api(self._context.application, self._context.get, server=server)
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
