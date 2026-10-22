"""The mounter turns scanned controllers into Ninja routes that call one shared controller instance."""

from collections.abc import Iterable
from itertools import count
from types import ModuleType
from typing import override

import pytest
import wireup
from ninja import NinjaAPI
from ninja.testing import TestClient
from wireup import injectable

from snakeboot.rest import (
    ControllerEndpointFactory,
    InvalidRestControllerError,
    RestControllerMounter,
    RestControllerScanner,
    error_answer,
    exception_handler,
    rest_controller,
    rest_controller_advice,
    route,
)
from snakeboot.rest.rest_controller_mappings import CONTROLLER_MAPPING_ATTRIBUTE
from tests.rest.sample_controllers.greeting_rest_controller import (
    Greeter,
    GreetingRestController,
    GreetingRestErrorAdvice,
)
from tests.rest.sample_controllers.nested.farewell_rest_controller import FarewellRestController

SAMPLES = "tests.rest.sample_controllers"
_api_numbers = count()


def new_api() -> NinjaAPI:
    return NinjaAPI(urls_namespace=f"rest-controllers-test-{next(_api_numbers)}")


@pytest.fixture
def mounted_api() -> NinjaAPI:
    """Both sample controllers, resolved from a real wireup container as singletons."""
    container = wireup.create_sync_container(
        injectables=[injectable(Greeter), GreetingRestController, FarewellRestController, GreetingRestErrorAdvice]
    )
    api = new_api()
    RestControllerMounter(endpoint_factory=ControllerEndpointFactory(container.get)).mount(api, scan=[SAMPLES])
    return api


def test_publishes_every_route_under_its_controller_prefix(mounted_api: NinjaAPI) -> None:
    paths = mounted_api.get_openapi_schema(path_prefix="")["paths"]

    assert {path: sorted(operations) for path, operations in paths.items()} == {
        "/greetings/{name}": ["get"],
        "/greetings": ["post"],
        "/farewells/{name}": ["get"],
    }


def test_no_self_parameter_reaches_the_api(mounted_api: NinjaAPI) -> None:
    paths = mounted_api.get_openapi_schema(path_prefix="")["paths"]
    parameter_names = [p["name"] for ops in paths.values() for op in ops.values() for p in op.get("parameters", [])]

    assert "self" not in parameter_names


def test_tags_default_to_the_class_name(mounted_api: NinjaAPI) -> None:
    paths = mounted_api.get_openapi_schema(path_prefix="")["paths"]

    assert paths["/farewells/{name}"]["get"]["tags"] == ["FarewellRestController"]
    assert paths["/greetings/{name}"]["get"]["tags"] == ["greetings"]


def test_every_request_is_served_by_the_same_singleton_controller(mounted_api: NinjaAPI) -> None:
    client = TestClient(mounted_api)

    first = client.get("/greetings/Ann").json()
    second = client.get("/greetings/Bob").json()
    posted = client.post("/greetings", json={"name": "Carol"})

    assert (first["message"], second["message"]) == ("Hallo Ann", "Hallo Bob")
    assert first["controller"] == second["controller"]
    assert (posted.status_code, posted.json()) == (201, {"message": "Hallo Carol"})


def test_ninja_still_validates_the_input(mounted_api: NinjaAPI) -> None:
    response = TestClient(mounted_api).post("/greetings", json={"nam": "x"})

    assert response.status_code == 422


@rest_controller("/empty")
class ControllerWithoutRoutes:
    """A controller someone forgot to give endpoints."""


class StubScanner(RestControllerScanner):
    """Test double: "finds" exactly the classes it was given that carry the asked marker."""

    def __init__(self, *classes: type) -> None:
        self._classes = list(classes)

    @override
    def scan(self, packages: Iterable[str | ModuleType], *, marker: str = CONTROLLER_MAPPING_ATTRIBUTE) -> list[type]:
        return [cls for cls in self._classes if marker in vars(cls)]


def test_a_controller_without_routes_stops_the_start_up() -> None:
    mounter = RestControllerMounter(scanner=StubScanner(ControllerWithoutRoutes))

    with pytest.raises(InvalidRestControllerError, match="no @route methods"):
        mounter.mount(new_api(), scan=["anything"])


def test_a_prefix_must_start_with_a_slash() -> None:
    with pytest.raises(InvalidRestControllerError):
        rest_controller("workshops")


def test_route_markers_only_record_and_leave_the_method_intact() -> None:
    @route.patch("/x", summary="partial update")
    def method(self, request) -> str:  # type: ignore[no-untyped-def]
        return "unchanged"

    assert method(None, None) == "unchanged"
    assert method.__rest_route_mapping__.http_method == "PATCH"  # type: ignore[attr-defined]
    assert method.__rest_route_mapping__.options == {"summary": "partial update"}  # type: ignore[attr-defined]


def test_an_advice_answers_the_errors_of_every_controller(mounted_api: NinjaAPI) -> None:
    response = TestClient(mounted_api).get("/greetings/nobody")

    assert response.status_code == 404
    assert response.json() == {"code": "unknown_name", "detail": "Nobody is not a name."}


def test_mount_reports_the_controllers_and_advices_it_found() -> None:
    mounted = RestControllerMounter(endpoint_factory=ControllerEndpointFactory(lambda _: None)).mount(
        new_api(), scan=[SAMPLES]
    )

    assert mounted.controllers == [GreetingRestController, FarewellRestController]
    assert mounted.advices == [GreetingRestErrorAdvice]


@rest_controller("/workshops")
class WorkshopsByWorkshopId:
    @route.get("/{workshop_id}")
    def get_workshop(self, request: object, workshop_id: str) -> None: ...


@rest_controller("/workshops/")
class WorkshopsById:
    @route.get("{id}")
    def find_workshop(self, request: object, id: str) -> None: ...  # noqa: A002  # reason: the path parameter under test


def test_two_endpoints_for_the_same_urls_stop_the_start_up() -> None:
    mounter = RestControllerMounter(scanner=StubScanner(WorkshopsByWorkshopId, WorkshopsById))

    with pytest.raises(InvalidRestControllerError, match=r"Ambiguous mapping: GET '/workshops/\{\}'"):
        mounter.mount(new_api(), scan=["anything"])


def test_the_same_path_with_another_http_method_is_not_ambiguous() -> None:
    mounter = RestControllerMounter(scanner=StubScanner(GreetingRestController, FarewellRestController))

    mounter.mount(new_api(), scan=["anything"])


class FirstError(Exception):
    pass


@rest_controller_advice
class FirstAdvice:
    @exception_handler(FirstError, status=409)
    def answer(self, error: Exception) -> dict[str, str]:
        return error_answer(error)


@rest_controller_advice
class SecondAdvice:
    @exception_handler(FirstError, status=422)
    def answer(self, error: Exception) -> dict[str, str]:
        return error_answer(error)


def test_two_advices_for_the_same_error_stop_the_start_up() -> None:
    mounter = RestControllerMounter(scanner=StubScanner(FirstAdvice, SecondAdvice))

    with pytest.raises(InvalidRestControllerError, match=r"FirstError is answered by FirstAdvice\.answer"):
        mounter.mount(new_api(), scan=["anything"])


def test_an_exception_handler_needs_an_error_type() -> None:
    with pytest.raises(InvalidRestControllerError, match="at least one error type"):
        exception_handler(status=400)


def test_error_answer_derives_a_stable_code_from_the_class_name() -> None:
    assert error_answer(FirstError("details")) == {"code": "first", "detail": "details"}
