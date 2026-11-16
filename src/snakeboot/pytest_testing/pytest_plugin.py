"""snakeboot's pytest plugin: an `@application_test` starts its application and gets what it asks for.

pytest loads it by itself, through the entry point `pytest11` of snakeboot. Until a test needs its application it
imports only pytest and `snakeboot.testing`, so a project without `@application_test`, or without a web server, loads
nothing more. Tests that ask the same application share one start of it, like Spring's test context cache
(`kept_applications`); between two tests it is reset, so each finds the database, the cache, the events, the mocks
and the test components as a fresh start leaves them. `@dirties_application` closes it after a test instead.
"""

from collections.abc import Iterator, Mapping
from typing import Final

import pytest

from snakeboot.pytest_testing.kept_applications import ApplicationSetUp, KeptApplications, RunningApplication
from snakeboot.testing.application_marker import (
    APPLICATION_TEST_FIXTURE,
    ApplicationTest,
    application_test_of,
    dirties_the_application,
    injected_fields_of,
    injected_parameters_of,
)
from snakeboot.testing.component_replacements import nested_test_components
from snakeboot.testing.injection import Injection, InjectionPoint
from snakeboot.testing.source_scan import ApplicationNotFoundError, ProjectSources

_SOURCES: Final = pytest.StashKey[ProjectSources]()
_KEPT_FIXTURE: Final = "snakeboot_kept_applications"


@pytest.fixture(name=_KEPT_FIXTURE, scope="session")
def kept_applications_fixture() -> Iterator[KeptApplications]:
    """Keeps the started applications of the run and closes them with its last test, inside what pytest captures:
    what closing logs is the last test's output, not the run's."""
    kept = KeptApplications()
    yield kept
    kept.close()


@pytest.fixture(name=APPLICATION_TEST_FIXTURE)
def application_test_fixture(request: pytest.FixtureRequest) -> Iterator[Mapping[str, object]]:
    """Hands an `@application_test` its started application: fills the fields of its class and its parameters."""
    fields = injected_fields_of(request.cls) if application_test_of(request.cls) is not None else {}
    parameters = injected_parameters_of(request.function)
    set_up = _set_up_of(request, [*fields.values(), *parameters.values()])
    kept: KeptApplications = request.getfixturevalue(_KEPT_FIXTURE)
    running = kept.running(set_up)
    try:
        for name, point in fields.items():
            setattr(request.instance, name, _injected(running, point))
        yield {name: _injected(running, point) for name, point in parameters.items()}
    finally:
        if _dirties(request):
            running.application.close()
        else:
            kept.keep(set_up, running)


@pytest.fixture(autouse=True)
def _application_of_a_test_class(request: pytest.FixtureRequest) -> None:
    """Starts the application for every test of an `@application_test` class, those without parameters included."""
    if application_test_of(request.cls) is not None:
        request.getfixturevalue(APPLICATION_TEST_FIXTURE)


def _marker_of(request: pytest.FixtureRequest) -> ApplicationTest:
    marker = application_test_of(request.function) or application_test_of(request.cls)
    if marker is None:
        pytest.fail(f"{request.node.name} asks for {APPLICATION_TEST_FIXTURE}, but is no @application_test.")
    return marker


def _set_up_of(request: pytest.FixtureRequest, points: list[InjectionPoint]) -> ApplicationSetUp:
    marker = _marker_of(request)
    sources = _sources_of(request.config)
    mocked = tuple(dict.fromkeys(point.component_type for point in points if point.injection is Injection.MOCK))
    return ApplicationSetUp(
        _application_of(marker, sources),
        marker.environment,
        marker.only,
        mocked=mocked,
        spied=tuple(dict.fromkeys(point.component_type for point in points if point.injection is Injection.SPY)),
        test_components={**sources.test_components(), **nested_test_components(_classes_of(request), mocked)},
    )


def _dirties(request: pytest.FixtureRequest) -> bool:
    return dirties_the_application(request.function) or dirties_the_application(request.cls)


def _classes_of(request: pytest.FixtureRequest) -> list[type]:
    """The class of the test and the classes it is nested in, the outermost first."""
    return [node.obj for node in request.node.listchain() if isinstance(node, pytest.Class)]


def _sources_of(config: pytest.Config) -> ProjectSources:
    if _SOURCES not in config.stash:
        config.stash[_SOURCES] = ProjectSources.scan()
    return config.stash[_SOURCES]


def _application_of(marker: ApplicationTest, sources: ProjectSources) -> type:
    if marker.application is not None:
        return marker.application
    try:
        return sources.application()
    except ApplicationNotFoundError as error:
        pytest.fail(str(error), pytrace=False)


def _injected(running: RunningApplication, point: InjectionPoint) -> object:
    from snakeboot.boot.testing import RestClient  # noqa: PLC0415  # reason: only a test that starts one needs it

    if point.injection is Injection.MOCK:
        return running.mocks[point.component_type]
    if point.component_type is RestClient:
        return running.application.client()
    return running.application.get(point.component_type)
