"""The controller scan turns the controllers of the component scan into Ninja routes on one shared instance."""

from itertools import count

import pytest
import wireup
from ninja import NinjaAPI
from ninja.testing import TestClient
from wireup import injectable

from snakeboot.component_scan import ComponentScan
from snakeboot.rest import (
    ControllerEndpointFactory,
    ControllerScan,
    InvalidRestControllerError,
    error_answer,
    exception_handler,
    rest_controller,
    route,
)
from tests.rest.ambiguous_advices.first_error_advices import FirstError
from tests.rest.sample_controllers.greeting_rest_controller import (
    Greeter,
    GreetingRestController,
    GreetingRestErrorAdvice,
)
from tests.rest.sample_controllers.nested.farewell_rest_controller import FarewellRestController

_api_numbers = count()


def scan_of(package: str) -> ComponentScan:
    return ComponentScan(base_packages=(f"tests.rest.{package}",), auto_configuration=())


SAMPLES = scan_of("sample_controllers")
NO_CONTAINER = ControllerEndpointFactory(lambda _: None)


def new_api() -> NinjaAPI:
    return NinjaAPI(urls_namespace=f"controller-scan-test-{next(_api_numbers)}")


@pytest.fixture
def api_with_samples() -> NinjaAPI:
    """Both sample controllers, resolved from a real wireup container as singletons."""
    container = wireup.create_sync_container(
        injectables=[injectable(Greeter), GreetingRestController, FarewellRestController, GreetingRestErrorAdvice]
    )
    api = new_api()
    ControllerScan(SAMPLES, endpoint_factory=ControllerEndpointFactory(container.get)).add_to(api)
    return api


def test_publishes_every_route_under_its_controller_prefix(api_with_samples: NinjaAPI) -> None:
    paths = api_with_samples.get_openapi_schema(path_prefix="")["paths"]

    assert {path: sorted(operations) for path, operations in paths.items()} == {
        "/greetings/{name}": ["get"],
        "/greetings": ["post"],
        "/farewells/{name}": ["get"],
    }


def test_no_self_parameter_reaches_the_api(api_with_samples: NinjaAPI) -> None:
    paths = api_with_samples.get_openapi_schema(path_prefix="")["paths"]
    parameter_names = [p["name"] for ops in paths.values() for op in ops.values() for p in op.get("parameters", [])]

    assert "self" not in parameter_names


def test_tags_default_to_the_class_name(api_with_samples: NinjaAPI) -> None:
    paths = api_with_samples.get_openapi_schema(path_prefix="")["paths"]

    assert paths["/farewells/{name}"]["get"]["tags"] == ["FarewellRestController"]
    assert paths["/greetings/{name}"]["get"]["tags"] == ["greetings"]


def test_every_request_is_served_by_the_same_singleton_controller(api_with_samples: NinjaAPI) -> None:
    client = TestClient(api_with_samples)

    first = client.get("/greetings/Ann").json()
    second = client.get("/greetings/Bob").json()
    posted = client.post("/greetings", json={"name": "Carol"})

    assert (first["message"], second["message"]) == ("Hallo Ann", "Hallo Bob")
    assert first["controller"] == second["controller"]
    assert (posted.status_code, posted.json()) == (201, {"message": "Hallo Carol"})


def test_ninja_still_validates_the_input(api_with_samples: NinjaAPI) -> None:
    response = TestClient(api_with_samples).post("/greetings", json={"nam": "x"})

    assert response.status_code == 422


def test_an_advice_answers_the_errors_of_every_controller(api_with_samples: NinjaAPI) -> None:
    response = TestClient(api_with_samples).get("/greetings/nobody")

    assert response.status_code == 404
    assert response.json() == {"code": "unknown_name", "detail": "Nobody is not a name."}


def test_reports_the_controllers_and_advices_once_where_they_are_declared_sorted_by_module() -> None:
    # sample_controllers/re_export.py imports GreetingRestController: it is still found once.
    scanned = ControllerScan(SAMPLES, endpoint_factory=NO_CONTAINER).add_to(new_api())

    assert scanned.controllers == [GreetingRestController, FarewellRestController]
    assert scanned.advices == [GreetingRestErrorAdvice]


def test_a_component_scan_without_controllers_adds_nothing() -> None:
    scanned = ControllerScan(ComponentScan(base_packages=("snakeboot.transaction",))).add_to(new_api())

    assert (scanned.controllers, scanned.advices) == ([], [])


def test_a_controller_without_routes_stops_the_start_up() -> None:
    with pytest.raises(InvalidRestControllerError, match="no @route methods"):
        ControllerScan(scan_of("without_routes"), endpoint_factory=NO_CONTAINER).add_to(new_api())


def test_two_endpoints_for_the_same_urls_stop_the_start_up() -> None:
    with pytest.raises(InvalidRestControllerError, match=r"Ambiguous mapping: GET '/workshops/\{\}'"):
        ControllerScan(scan_of("ambiguous_routes"), endpoint_factory=NO_CONTAINER).add_to(new_api())


def test_two_advices_for_the_same_error_stop_the_start_up() -> None:
    with pytest.raises(InvalidRestControllerError, match=r"FirstError is answered by FirstAdvice\.answer"):
        ControllerScan(scan_of("ambiguous_advices"), endpoint_factory=NO_CONTAINER).add_to(new_api())


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


def test_an_exception_handler_needs_an_error_type() -> None:
    with pytest.raises(InvalidRestControllerError, match="at least one error type"):
        exception_handler(status=400)


def test_error_answer_derives_a_stable_code_from_the_class_name() -> None:
    assert error_answer(FirstError("details")) == {"code": "first", "detail": "details"}
