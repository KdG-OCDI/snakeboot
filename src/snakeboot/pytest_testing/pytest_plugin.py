"""snakeboot's pytest plugin: an `@application_test` starts its application and gets what it asks for.

pytest loads it by itself, through the entry point `pytest11` of snakeboot. Until a test needs its application it
imports only pytest and `snakeboot.testing`, so a project without `@application_test`, or without a web server, loads
nothing more. Every test gets its own application, with fresh test components and mocks: nothing to clean up between
tests, where Spring keeps one context and empties it.
"""

from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Any, Final
from unittest.mock import create_autospec

import pytest

from snakeboot.testing.application_marker import (
    APPLICATION_TEST_FIXTURE,
    ApplicationTest,
    application_test_of,
    injected_fields_of,
    injected_parameters_of,
)
from snakeboot.testing.injection import Injection, InjectionPoint
from snakeboot.testing.source_scan import ApplicationNotFoundError, ProjectSources

if TYPE_CHECKING:
    from snakeboot.boot.testing import TestApplication

_SOURCES: Final = pytest.StashKey[ProjectSources]()


@pytest.fixture(name=APPLICATION_TEST_FIXTURE)
def application_test_fixture(request: pytest.FixtureRequest) -> Iterator[Mapping[str, object]]:
    """Starts the application of an `@application_test` for one test, fills its fields and hands its parameters."""
    from snakeboot.boot.testing import TestApplication  # noqa: PLC0415  # reason: only a test that starts one needs it

    marker = _marker_of(request)
    fields = injected_fields_of(request.cls) if application_test_of(request.cls) is not None else {}
    parameters = injected_parameters_of(request.function)
    points = [*fields.values(), *parameters.values()]
    mocks = {p.component_type: create_autospec(p.component_type, instance=True) for p in points if _is(p, "MOCK")}
    sources = _sources_of(request.config)
    with TestApplication.start(
        _application_of(marker, sources),
        mocks,
        environment=marker.environment,
        only=marker.only,
        test_components={replaced: _built(component) for replaced, component in sources.test_components().items()},
    ) as started:
        for point in points:
            if _is(point, "SPY"):
                started.spy(point.component_type)
        for name, point in fields.items():
            setattr(request.instance, name, _injected(started, mocks, point))
        yield {name: _injected(started, mocks, point) for name, point in parameters.items()}


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


def _built(component: type) -> object:
    try:
        return component()
    except TypeError as error:
        raise TypeError(f"A test component is built without arguments; {component.__qualname__}: {error}") from error


def _is(point: InjectionPoint, injection: str) -> bool:
    return point.injection is Injection[injection]


def _injected(started: "TestApplication", mocks: Mapping[Any, object], point: InjectionPoint) -> object:
    from snakeboot.boot.testing import RestClient  # noqa: PLC0415  # reason: as TestApplication above

    if point.injection is Injection.MOCK:
        return mocks[point.component_type]
    if point.component_type is RestClient:
        return started.client()
    return started.get(point.component_type)
