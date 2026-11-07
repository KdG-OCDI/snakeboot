"""A Ninja view shows Ninja the request and what the call carries, and calls the method on the resolved controller."""

import inspect
from types import SimpleNamespace

import pytest

from snakeboot.component_scan import ComponentScan
from snakeboot.django_ninja import NinjaEndpointFactory, principal_of
from snakeboot.rest import ControllerScan, DeclaredEndpoint, NoAuthenticatedPrincipalError, Principal
from tests.rest.sample_controllers.greeting_rest_controller import Greeter, GreetingRestController
from tests.rest.secured.who_am_i_rest_controller import WhoAmIRestController


def endpoint_named(name: str, package: str) -> DeclaredEndpoint:
    scanned = ControllerScan(ComponentScan((f"tests.rest.{package}",), auto_configuration=())).find()
    return next(endpoint for endpoint in scanned.endpoints if endpoint.method.__name__ == name)


def test_shows_ninja_the_request_and_the_parameters_the_call_carries() -> None:
    view = NinjaEndpointFactory(lambda _: None).create(endpoint_named("greet", "sample_controllers"))

    assert list(inspect.signature(view).parameters) == ["request", "name"]
    assert view.__name__ == "greet"


def test_hides_the_principal_from_ninja() -> None:
    view = NinjaEndpointFactory(lambda _: None).create(endpoint_named("who_am_i", "secured"))

    assert list(inspect.signature(view).parameters) == ["request"]


def test_calls_the_method_on_the_controller_the_resolver_returns_without_the_request() -> None:
    controller = GreetingRestController(Greeter())
    resolved: list[type] = []

    def resolve(controller_class: type) -> object:
        resolved.append(controller_class)
        return controller

    view = NinjaEndpointFactory(resolve).create(endpoint_named("greet", "sample_controllers"))

    assert view(SimpleNamespace(), name="Ann")["message"] == "Hallo Ann"
    assert resolved == [GreetingRestController]


def test_fills_the_principal_from_what_the_authentication_stored() -> None:
    view = NinjaEndpointFactory(lambda _: WhoAmIRestController()).create(endpoint_named("who_am_i", "secured"))

    assert view(SimpleNamespace(auth="bob")) == {"name": "bob"}


def test_the_principal_is_the_id_of_the_authentication() -> None:
    assert principal_of(SimpleNamespace(auth="carol")) == Principal("carol")  # type: ignore[arg-type]


@pytest.mark.parametrize("request_", [SimpleNamespace(), SimpleNamespace(auth=42)], ids=["no auth", "no id"])
def test_without_an_id_there_is_no_principal(request_: SimpleNamespace) -> None:
    with pytest.raises(NoAuthenticatedPrincipalError):
        principal_of(request_)  # type: ignore[arg-type]
