"""A FastAPI view shows FastAPI only the parameters a call carries, and calls the controller's method."""

import inspect

import pytest

from snakeboot.component_scan import ComponentScan
from snakeboot.fastapi_web import BearerToken, FastApiEndpointFactory
from snakeboot.fastapi_web.fastapi_endpoint_factory import PRINCIPAL_PARAMETER
from snakeboot.rest import ControllerScan, DeclaredEndpoint, NoAuthenticatedPrincipalError
from tests.rest.secured.who_am_i_rest_controller import WhoAmIRestController


def endpoint_named(name: str) -> DeclaredEndpoint:
    scanned = ControllerScan(ComponentScan(("tests.rest.secured",), auto_configuration=())).find()
    return next(endpoint for endpoint in scanned.endpoints if endpoint.method.__name__ == name)


def factory(*, bearer: bool) -> FastApiEndpointFactory:
    resolve = lambda _: WhoAmIRestController()  # noqa: E731  # reason: a one-line resolver
    return FastApiEndpointFactory(resolve, BearerToken(resolve) if bearer else None)


def test_hides_self_and_the_principal_and_asks_for_the_bearer_token_instead() -> None:
    view = factory(bearer=True).create(endpoint_named("who_am_i"))

    assert list(inspect.signature(view).parameters) == [PRINCIPAL_PARAMETER]


def test_a_public_endpoint_asks_for_no_token() -> None:
    view = factory(bearer=True).create(endpoint_named("open_door"))

    assert list(inspect.signature(view).parameters) == []


def test_fills_the_principal_with_the_id_the_bearer_token_found() -> None:
    view = factory(bearer=True).create(endpoint_named("who_am_i"))

    assert view(**{PRINCIPAL_PARAMETER: "alice"}) == {"name": "alice"}


def test_without_an_id_there_is_no_principal() -> None:
    view = factory(bearer=True).create(endpoint_named("who_am_i"))

    with pytest.raises(NoAuthenticatedPrincipalError, match="Expected the id of a signed-in principal"):
        view()
