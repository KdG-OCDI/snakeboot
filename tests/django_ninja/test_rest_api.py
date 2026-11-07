"""On Django Ninja, the controllers of the component scan answer HTTP calls, on one shared instance each."""

import json
from itertools import count

import pytest
import wireup
from django.test import RequestFactory
from django.urls import URLPattern
from ninja import NinjaAPI
from ninja.testing import TestClient
from wireup import injectable

from snakeboot.django_ninja import rest_api, url_patterns
from snakeboot.rest import InvalidRestControllerError
from tests.rest.sample_application import (
    DoublySecuredApplication,
    GreetingApplication,
    SecuredApplication,
    UndescribedApplication,
)
from tests.rest.sample_controllers.greeting_rest_controller import (
    Greeter,
    GreetingRestController,
    GreetingRestErrorAdvice,
)
from tests.rest.sample_controllers.nested.farewell_rest_controller import FarewellRestController
from tests.rest.secured import token_checker
from tests.rest.secured.who_am_i_rest_controller import WhoAmIRestController

_namespaces = count()


@pytest.fixture
def container() -> wireup.SyncContainer:
    """Every sample controller and advice, the greeter and the token checker, as singletons."""
    return wireup.create_sync_container(
        injectables=[
            injectable(Greeter),
            GreetingRestController,
            FarewellRestController,
            GreetingRestErrorAdvice,
            WhoAmIRestController,
            token_checker,
        ]
    )


def api_of(application: type, container: wireup.SyncContainer) -> NinjaAPI:
    api = rest_api(application, resolve=container.get)
    api.urls_namespace = f"rest-api-test-{next(_namespaces)}"
    return api


@pytest.fixture
def client(container: wireup.SyncContainer) -> TestClient:
    return TestClient(api_of(GreetingApplication, container))


@pytest.fixture
def secured(container: wireup.SyncContainer) -> TestClient:
    return TestClient(api_of(SecuredApplication, container))


def test_publishes_every_route_under_its_controller_prefix(container: wireup.SyncContainer) -> None:
    paths = api_of(GreetingApplication, container).get_openapi_schema(path_prefix="")["paths"]

    assert {path: sorted(operations) for path, operations in paths.items()} == {
        "/greetings/{name}": ["delete", "get"],
        "/greetings": ["post"],
        "/farewells/{name}": ["get"],
    }


def test_neither_self_nor_the_request_reaches_the_api(container: wireup.SyncContainer) -> None:
    paths = api_of(GreetingApplication, container).get_openapi_schema(path_prefix="")["paths"]
    parameter_names = [p["name"] for ops in paths.values() for op in ops.values() for p in op.get("parameters", [])]

    assert set(parameter_names) == {"name"}


def test_the_tags_are_those_of_the_controllers(container: wireup.SyncContainer) -> None:
    paths = api_of(GreetingApplication, container).get_openapi_schema(path_prefix="")["paths"]

    assert paths["/farewells/{name}"]["get"]["tags"] == ["FarewellRestController"]
    assert paths["/greetings/{name}"]["get"]["tags"] == ["greetings"]


def test_the_return_annotation_describes_the_answer(container: wireup.SyncContainer) -> None:
    operation = api_of(GreetingApplication, container).get_openapi_schema(path_prefix="")["paths"]["/greetings"]

    assert list(operation["post"]["responses"]) == [201]


def test_every_request_is_served_by_the_same_singleton_controller(client: TestClient) -> None:
    first = client.get("/greetings/Ann").json()
    second = client.get("/greetings/Bob").json()

    assert (first["message"], second["message"]) == ("Hallo Ann", "Hallo Bob")
    assert first["controller"] == second["controller"]


def test_the_status_of_the_route_answers_a_body(client: TestClient) -> None:
    posted = client.post("/greetings", json={"name": "Carol"})

    assert (posted.status_code, posted.json()) == (201, {"message": "Hallo Carol"})


def test_a_method_that_returns_none_answers_without_a_body(client: TestClient) -> None:
    deleted = client.delete("/greetings/Dave")

    assert (deleted.status_code, deleted.content) == (204, b"")


def test_ninja_still_validates_the_input(client: TestClient) -> None:
    assert client.post("/greetings", json={"nam": "x"}).status_code == 422


def test_an_advice_answers_the_errors_of_every_controller(client: TestClient) -> None:
    response = client.get("/greetings/nobody")

    assert response.status_code == 404
    assert response.json() == {"code": "unknown_name", "detail": "Nobody is not a name."}


def test_openapi_definition_describes_the_api(container: wireup.SyncContainer) -> None:
    info = api_of(GreetingApplication, container).get_openapi_schema(path_prefix="")["info"]

    assert (info["title"], info["version"], info["description"]) == ("Greetings", "2.1.0", "Says hello and goodbye.")


def test_without_openapi_definition_the_api_has_ninja_s_defaults(container: wireup.SyncContainer) -> None:
    info = api_of(UndescribedApplication, container).get_openapi_schema(path_prefix="")["info"]

    assert info["title"] == "NinjaAPI"


def test_health_answers_with_the_name_of_the_application_package() -> None:
    health = next(pattern for pattern in url_patterns(GreetingApplication) if isinstance(pattern, URLPattern)).callback

    answer = health(RequestFactory().get("/health"))

    assert answer.status_code == 200
    assert json.loads(answer.content) == {"status": "ok", "service": "rest"}


def test_a_call_without_a_token_is_refused(secured: TestClient) -> None:
    assert secured.get("/greetings/Ann").status_code == 401


def test_a_call_with_a_token_the_authentication_refuses_is_refused(secured: TestClient) -> None:
    assert secured.get("/greetings/Ann", headers={"Authorization": "Bearer bad-token"}).status_code == 401


def test_a_call_with_an_accepted_token_reaches_the_controller(secured: TestClient) -> None:
    response = secured.get("/greetings/Ann", headers={"Authorization": "Bearer good-token"})

    assert (response.status_code, response.json()["message"]) == (200, "Hallo Ann")


def test_an_endpoint_receives_whom_the_token_belongs_to_as_its_principal(secured: TestClient) -> None:
    response = secured.get("/me", headers={"Authorization": "Bearer good-token"})

    assert response.json() == {"name": "alice"}


def test_a_public_endpoint_answers_without_a_token(secured: TestClient) -> None:
    assert secured.get("/me/door").json() == {"door": "open"}


def test_the_openapi_document_shows_the_bearer_token(container: wireup.SyncContainer) -> None:
    schema = api_of(SecuredApplication, container).get_openapi_schema(path_prefix="")

    assert schema["components"]["securitySchemes"]["BearerToken"] == {"type": "http", "scheme": "bearer"}
    assert schema["paths"]["/greetings/{name}"]["get"]["security"] == [{"BearerToken": []}]
    assert "security" not in schema["paths"]["/me/door"]["get"]


def test_two_authentications_in_the_component_scan_stop_the_start() -> None:
    with pytest.raises(InvalidRestControllerError, match="one BearerAuthentication, the component scan declares"):
        rest_api(DoublySecuredApplication)
