"""A `BearerAuthentication` in the component scan checks the bearer token of every endpoint."""

from itertools import count

import pytest
import wireup
from django.core.exceptions import ImproperlyConfigured
from ninja import NinjaAPI
from ninja.testing import TestClient
from wireup import injectable

from snakeboot.rest import BearerAuthentication, rest_api
from tests.rest.sample_application import DoublySecuredApplication, SecuredApplication
from tests.rest.sample_controllers.greeting_rest_controller import (
    Greeter,
    GreetingRestController,
    GreetingRestErrorAdvice,
)
from tests.rest.sample_controllers.nested.farewell_rest_controller import FarewellRestController
from tests.rest.secured import token_checker
from tests.rest.secured.token_checker import TokenChecker

_namespaces = count()


@pytest.fixture
def container() -> wireup.SyncContainer:
    return wireup.create_sync_container(
        injectables=[
            injectable(Greeter),
            GreetingRestController,
            FarewellRestController,
            GreetingRestErrorAdvice,
            token_checker,
        ]
    )


@pytest.fixture
def secured_api(container: wireup.SyncContainer) -> NinjaAPI:
    api = rest_api(SecuredApplication, resolve=container.get)
    api.urls_namespace = f"bearer-authentication-test-{next(_namespaces)}"
    return api


def test_a_subclass_is_a_component_of_the_container(container: wireup.SyncContainer) -> None:
    assert isinstance(container.get(BearerAuthentication), TokenChecker)


def test_an_abstract_subclass_is_not_registered() -> None:
    class StillAbstract(BearerAuthentication):
        pass

    assert "__wireup_registration__" not in vars(StillAbstract)


def test_a_call_without_a_token_is_refused(secured_api: NinjaAPI) -> None:
    assert TestClient(secured_api).get("/greetings/Ann").status_code == 401


def test_a_call_with_a_token_the_authentication_refuses_is_refused(secured_api: NinjaAPI) -> None:
    response = TestClient(secured_api).get("/greetings/Ann", headers={"Authorization": "Bearer bad-token"})

    assert response.status_code == 401


def test_a_call_with_an_accepted_token_reaches_the_controller(secured_api: NinjaAPI) -> None:
    response = TestClient(secured_api).get("/greetings/Ann", headers={"Authorization": "Bearer good-token"})

    assert response.status_code == 200
    assert response.json()["message"] == "Hallo Ann"


def test_the_openapi_document_shows_the_bearer_token(secured_api: NinjaAPI) -> None:
    schema = secured_api.get_openapi_schema(path_prefix="")

    assert schema["components"]["securitySchemes"]["BearerToken"] == {"type": "http", "scheme": "bearer"}
    assert schema["paths"]["/greetings/{name}"]["get"]["security"] == [{"BearerToken": []}]


def test_two_authentications_in_the_component_scan_stop_the_start() -> None:
    with pytest.raises(ImproperlyConfigured, match="one BearerAuthentication, the component scan declares"):
        rest_api(DoublySecuredApplication)
