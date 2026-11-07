"""The controller scan finds and checks the REST API of a component scan, without any web framework."""

import pytest

from snakeboot.component_scan import ComponentScan
from snakeboot.rest import (
    ControllerScan,
    InvalidRestControllerError,
    RouteMapping,
    error_answer,
    exception_handler,
    rest_controller,
    route,
)
from tests.rest.ambiguous_advices.first_error_advices import FirstError
from tests.rest.sample_controllers.greeting_rest_controller import GreetingRestController, GreetingRestErrorAdvice
from tests.rest.sample_controllers.nested.farewell_rest_controller import FarewellRestController
from tests.rest.secured.token_checker import TokenChecker


def scan_of(*packages: str) -> ControllerScan:
    return ControllerScan(ComponentScan(tuple(f"tests.rest.{package}" for package in packages), auto_configuration=()))


def test_finds_the_controllers_and_advices_once_where_they_are_declared_sorted_by_module() -> None:
    # sample_controllers/re_export.py imports GreetingRestController: it is still found once.
    scanned = scan_of("sample_controllers").find()

    assert scanned.controllers == [GreetingRestController, FarewellRestController]
    assert scanned.advices == [GreetingRestErrorAdvice]


def test_finds_every_endpoint_with_its_full_route() -> None:
    scanned = scan_of("sample_controllers").find()

    assert sorted(endpoint.route_key for endpoint in scanned.endpoints) == [
        ("DELETE", "/greetings/{}"),
        ("GET", "/farewells/{}"),
        ("GET", "/greetings/{}"),
        ("POST", "/greetings"),
    ]
    assert [endpoint.name for endpoint in scanned.endpoints_of(FarewellRestController)] == [
        "FarewellRestController.say_goodbye"
    ]


def test_tags_default_to_the_class_name() -> None:
    scanned = scan_of("sample_controllers").find()

    assert scanned.mapping_of(FarewellRestController).tags == ("FarewellRestController",)
    assert scanned.mapping_of(GreetingRestController).tags == ("greetings",)


def test_finds_the_error_answers_of_the_advices() -> None:
    [handler] = scan_of("sample_controllers").find().error_handlers

    assert handler.name == "GreetingRestErrorAdvice.answer_unknown_name"
    assert handler.mapping.status == 404


def test_finds_the_authentication_of_the_api() -> None:
    assert scan_of("sample_controllers").find().authentication is None
    assert scan_of("sample_controllers", "secured").find().authentication is TokenChecker


def test_a_component_scan_without_controllers_finds_nothing() -> None:
    scanned = ControllerScan(ComponentScan(base_packages=("snakeboot.transaction",))).find()

    assert (scanned.controllers, scanned.advices, scanned.endpoints, scanned.error_handlers) == ([], [], [], [])
    assert scanned.authentication is None


def test_a_controller_without_routes_stops_the_start_up() -> None:
    with pytest.raises(InvalidRestControllerError, match="no @route methods"):
        scan_of("without_routes").find()


def test_two_endpoints_for_the_same_urls_stop_the_start_up() -> None:
    with pytest.raises(InvalidRestControllerError, match=r"Ambiguous mapping: GET '/workshops/\{\}'"):
        scan_of("ambiguous_routes").find()


def test_two_advices_for_the_same_error_stop_the_start_up() -> None:
    with pytest.raises(InvalidRestControllerError, match=r"FirstError is answered by FirstAdvice\.answer"):
        scan_of("ambiguous_advices").find()


def test_two_authentications_stop_the_start_up() -> None:
    with pytest.raises(InvalidRestControllerError, match="one BearerAuthentication, the component scan declares"):
        scan_of("doubly_secured").find()


def test_a_public_endpoint_that_asks_for_a_principal_stops_the_start_up() -> None:
    with pytest.raises(InvalidRestControllerError, match=r"PublicRestController\.who_am_i is public"):
        scan_of("public_principal").find()


def test_a_principal_without_an_authentication_stops_the_start_up() -> None:
    with pytest.raises(InvalidRestControllerError, match="declares no BearerAuthentication"):
        scan_of("principal_without_authentication").find()


def test_a_prefix_must_start_with_a_slash() -> None:
    with pytest.raises(InvalidRestControllerError):
        rest_controller("workshops")


def test_route_markers_only_record_and_leave_the_method_intact() -> None:
    @route.patch("/x", status=202, public=True)
    def method(self: object) -> str:
        return "unchanged"

    assert method(None) == "unchanged"
    assert method.__rest_route_mapping__ == RouteMapping("PATCH", "/x", status=202, public=True)  # type: ignore[attr-defined]


def test_a_route_takes_no_option_it_does_not_know() -> None:
    with pytest.raises(TypeError, match="auth"):
        route.get("/x", auth=None)  # type: ignore[call-arg]


def test_an_exception_handler_needs_an_error_type() -> None:
    with pytest.raises(InvalidRestControllerError, match="at least one error type"):
        exception_handler(status=400)


def test_error_answer_derives_a_stable_code_from_the_class_name() -> None:
    assert error_answer(FirstError("details")) == {"code": "first", "detail": "details"}
