"""`@roles_allowed` names the roles of which a caller needs one, on a controller or on one of its endpoints."""

from dataclasses import replace

import pytest

from snakeboot.component_scan import ComponentScan
from snakeboot.rest import ControllerScan, InvalidRestControllerError, roles_allowed
from snakeboot.security import Principal


def scan_of(package: str) -> ControllerScan:
    return ControllerScan(ComponentScan((f"tests.rest.{package}",), auto_configuration=()))


def roles_by_endpoint() -> dict[str, frozenset[str]]:
    return {endpoint.method.__name__: endpoint.roles for endpoint in scan_of("role_secured").find().endpoints}


def test_an_endpoint_needs_the_roles_of_its_controller() -> None:
    assert roles_by_endpoint()["list_workshops"] == frozenset({"organizer"})


def test_the_roles_of_an_endpoint_replace_those_of_its_controller() -> None:
    assert roles_by_endpoint()["cancel_workshop"] == frozenset({"organizer", "moderator"})


def test_a_public_endpoint_of_a_controller_with_roles_needs_none() -> None:
    assert roles_by_endpoint()["catalogue"] == frozenset()


def test_an_endpoint_without_roles_lets_in_any_authenticated_caller() -> None:
    endpoints = ControllerScan(ComponentScan(("tests.rest.secured",), auto_configuration=())).find().endpoints

    assert {endpoint.roles for endpoint in endpoints} == {frozenset()}


def test_roles_on_a_public_endpoint_stop_the_start_up() -> None:
    with pytest.raises(InvalidRestControllerError, match=r"PublicRolesRestController\.everybody is public"):
        scan_of("public_roles").find()


def test_roles_without_an_authentication_stop_the_start_up() -> None:
    with pytest.raises(InvalidRestControllerError, match="names roles, but the component scan declares no"):
        scan_of("roles_without_authentication").find()


def test_roles_allowed_names_a_role_at_least() -> None:
    with pytest.raises(InvalidRestControllerError, match="names one role or more"):
        roles_allowed()


def test_a_principal_has_the_roles_it_was_granted() -> None:
    principal = Principal("olivia", roles=frozenset({"organizer"}))

    assert principal.has_role("organizer")
    assert not principal.has_role("moderator")
    assert principal.has_any_role(["moderator", "organizer"])
    assert not Principal("pat").has_any_role(["organizer"])


def test_roles_on_a_method_of_a_service_stop_the_start_up() -> None:
    with pytest.raises(InvalidRestControllerError, match=r"SecuredService\.execute names roles, but is no endpoint"):
        ControllerScan(
            ComponentScan(("tests.rest.roles_on_a_service",), exclude=("*.secured_class",), auto_configuration=())
        ).find()


def test_roles_on_a_class_that_is_no_controller_stop_the_start_up() -> None:
    with pytest.raises(InvalidRestControllerError, match=r"SecuredClass names roles, but is no @rest_controller"):
        ControllerScan(
            ComponentScan(("tests.rest.roles_on_a_service",), exclude=("*.secured_service",), auto_configuration=())
        ).find()


def test_roles_on_a_method_of_a_controller_that_is_no_endpoint_stop_the_start_up() -> None:
    with pytest.raises(InvalidRestControllerError, match=r"HelperRestController\.helper names roles, but is no"):
        scan_of("roles_on_a_helper_method").find()


def test_an_application_without_controllers_or_roles_scans_to_an_empty_api() -> None:
    only_a_token_checker = ComponentScan(("tests.rest.roles_on_a_service",), exclude=("*.secured_*",))
    scanned = ControllerScan(replace(only_a_token_checker, auto_configuration=())).find()

    assert (scanned.controllers, scanned.endpoints) == ([], [])
