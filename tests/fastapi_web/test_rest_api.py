"""On FastAPI, the controllers of the component scan answer HTTP calls, on one shared instance each."""

from typing import Any

import pytest
import wireup
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from wireup import injectable

from snakeboot.configuration import ServerProperties
from snakeboot.fastapi_web import invalid_request_of, rest_api
from snakeboot.rest import InvalidRestControllerError, RequestProblem
from tests.rest.sample_application import (
    DoublySecuredApplication,
    GreetingApplication,
    SecuredApplication,
    UnadvisedApplication,
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
from tests.rest.unadvised.echo_rest_controller import EchoRestController


@injectable
def greeter() -> Greeter:
    return Greeter()


@pytest.fixture
def container() -> wireup.SyncContainer:
    """Every sample controller and advice, the greeter and the token checker, as singletons."""
    return wireup.create_sync_container(
        injectables=[
            greeter,
            GreetingRestController,
            FarewellRestController,
            GreetingRestErrorAdvice,
            WhoAmIRestController,
            token_checker,
        ]
    )


def schema_of(application: type, container: wireup.SyncContainer) -> dict[str, Any]:
    return rest_api(application, container.get).openapi()


@pytest.fixture
def client(container: wireup.SyncContainer) -> TestClient:
    return TestClient(rest_api(GreetingApplication, container.get))


@pytest.fixture
def secured(container: wireup.SyncContainer) -> TestClient:
    return TestClient(rest_api(SecuredApplication, container.get))


def test_publishes_every_route_under_its_controller_prefix_below_api(container: wireup.SyncContainer) -> None:
    paths = schema_of(GreetingApplication, container)["paths"]

    assert {path: sorted(operations) for path, operations in paths.items()} == {
        "/api/greetings/{name}": ["delete", "get"],
        "/api/greetings": ["post"],
        "/api/farewells/{name}": ["get"],
    }


def test_neither_self_nor_a_principal_reaches_the_api(container: wireup.SyncContainer) -> None:
    paths = schema_of(SecuredApplication, container)["paths"]
    parameter_names = [p["name"] for ops in paths.values() for op in ops.values() for p in op.get("parameters", [])]

    assert set(parameter_names) == {"name"}


def test_the_tags_are_those_of_the_controllers(container: wireup.SyncContainer) -> None:
    paths = schema_of(GreetingApplication, container)["paths"]

    assert paths["/api/farewells/{name}"]["get"]["tags"] == ["FarewellRestController"]
    assert paths["/api/greetings/{name}"]["get"]["tags"] == ["greetings"]


def test_the_return_annotation_describes_the_answer(container: wireup.SyncContainer) -> None:
    responses = schema_of(GreetingApplication, container)["paths"]["/api/greetings"]["post"]["responses"]

    assert list(responses) == ["201", "422"]
    assert responses["201"]["content"]["application/json"]["schema"]["type"] == "object"


def test_every_request_is_served_by_the_same_singleton_controller(client: TestClient) -> None:
    first = client.get("/api/greetings/Ann").json()
    second = client.get("/api/greetings/Bob").json()

    assert (first["message"], second["message"]) == ("Hallo Ann", "Hallo Bob")
    assert first["controller"] == second["controller"]


def test_the_status_of_the_route_answers_a_body(client: TestClient) -> None:
    posted = client.post("/api/greetings", json={"name": "Carol"})

    assert (posted.status_code, posted.json()) == (201, {"message": "Hallo Carol"})


def test_a_method_that_returns_none_answers_without_a_body(client: TestClient) -> None:
    deleted = client.delete("/api/greetings/Dave")

    assert (deleted.status_code, deleted.content) == (204, b"")


def test_a_call_that_does_not_fit_is_an_invalid_request_the_advice_answers(client: TestClient) -> None:
    response = client.post("/api/greetings", json={"nam": "x"})

    assert response.status_code == 422
    assert response.json() == {"code": "invalid_request", "detail": "body.name: Field required"}


def test_without_an_advice_for_it_an_invalid_request_is_fastapi_s_422() -> None:
    response = TestClient(rest_api(UnadvisedApplication, lambda _: EchoRestController())).post("/api/echo", json={})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "text"]


def test_fastapi_s_validation_error_becomes_one_request_problem_per_error() -> None:
    error = invalid_request_of(
        RequestValidationError([{"loc": ("query", "cells", 2), "msg": "too big"}, {"loc": ("body",), "msg": "missing"}])
    )

    assert error.problems == (RequestProblem(("query", "cells", "2"), "too big"), RequestProblem(("body",), "missing"))
    assert str(error) == "query.cells.2: too big; body: missing"


def test_an_advice_answers_the_errors_of_every_controller(client: TestClient) -> None:
    response = client.get("/api/greetings/nobody")

    assert response.status_code == 404
    assert response.json() == {"code": "unknown_name", "detail": "Nobody is not a name."}


def test_openapi_definition_describes_the_api(container: wireup.SyncContainer) -> None:
    info = schema_of(GreetingApplication, container)["info"]

    assert (info["title"], info["version"], info["description"]) == ("Greetings", "2.1.0", "Says hello and goodbye.")


def test_without_openapi_definition_the_api_has_fastapi_s_defaults(container: wireup.SyncContainer) -> None:
    assert schema_of(UndescribedApplication, container)["info"]["title"] == "FastAPI"


def test_swagger_ui_and_the_openapi_document_live_below_api(client: TestClient) -> None:
    assert client.get("/api/docs").status_code == 200
    assert client.get("/api/openapi.json").json()["info"]["title"] == "Greetings"


def test_health_answers_with_the_name_of_the_application_package(client: TestClient) -> None:
    answer = client.get("/health")

    assert (answer.status_code, answer.json()) == (200, {"status": "ok", "service": "rest"})


def test_health_answers_without_a_token(secured: TestClient) -> None:
    assert secured.get("/health").status_code == 200


def test_a_call_without_a_token_is_refused(secured: TestClient) -> None:
    response = secured.get("/api/greetings/Ann")

    assert (response.status_code, response.json()) == (401, {"detail": "Unauthorized"})
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_a_call_with_a_token_the_authentication_refuses_is_refused(secured: TestClient) -> None:
    assert secured.get("/api/greetings/Ann", headers={"Authorization": "Bearer bad-token"}).status_code == 401


def test_a_call_with_an_accepted_token_reaches_the_controller(secured: TestClient) -> None:
    response = secured.get("/api/greetings/Ann", headers={"Authorization": "Bearer good-token"})

    assert (response.status_code, response.json()["message"]) == (200, "Hallo Ann")


def test_an_endpoint_receives_whom_the_token_belongs_to_as_its_principal(secured: TestClient) -> None:
    response = secured.get("/api/me", headers={"Authorization": "Bearer good-token"})

    assert response.json() == {"name": "alice"}


def test_a_public_endpoint_answers_without_a_token(secured: TestClient) -> None:
    assert secured.get("/api/me/door").json() == {"door": "open"}


def test_the_openapi_document_shows_the_bearer_token(container: wireup.SyncContainer) -> None:
    schema = schema_of(SecuredApplication, container)

    assert schema["components"]["securitySchemes"]["BearerToken"] == {"type": "http", "scheme": "bearer"}
    assert schema["paths"]["/api/greetings/{name}"]["get"]["security"] == [{"BearerToken": []}]
    assert "security" not in schema["paths"]["/api/me/door"]["get"]


def test_two_authentications_in_the_component_scan_stop_the_start() -> None:
    with pytest.raises(InvalidRestControllerError, match="one BearerAuthentication, the component scan declares"):
        rest_api(DoublySecuredApplication, lambda _: None)


def server(*, allowed_hosts: tuple[str, ...], debug: bool = False) -> ServerProperties:
    return ServerProperties(debug=debug, allowed_hosts=allowed_hosts, log_level="INFO")


def test_the_server_answers_only_its_allowed_hosts(container: wireup.SyncContainer) -> None:
    api: FastAPI = rest_api(GreetingApplication, container.get, server=server(allowed_hosts=("games.example",)))

    assert TestClient(api).get("/health").status_code == 400
    assert TestClient(api, base_url="http://games.example").get("/health").status_code == 200


def test_the_server_s_debug_turns_on_fastapi_s_debug(container: wireup.SyncContainer) -> None:
    assert rest_api(GreetingApplication, container.get, server=server(allowed_hosts=("*",), debug=True)).debug
