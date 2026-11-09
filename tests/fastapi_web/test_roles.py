"""On FastAPI, `@roles_allowed` answers 403 to a caller without one of its roles, and the caller is signed in."""

import pytest
import wireup
from fastapi.testclient import TestClient

from snakeboot.fastapi_web import rest_api
from tests.rest.role_secured import role_tokens
from tests.rest.role_secured.workshop_admin_rest_controller import WorkshopAdminRestController
from tests.rest.sample_application import RoleSecuredApplication


@pytest.fixture
def client() -> TestClient:
    container = wireup.create_sync_container(injectables=[WorkshopAdminRestController, role_tokens])
    return TestClient(rest_api(RoleSecuredApplication, container.get))


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_a_caller_with_the_role_of_the_controller_is_let_in(client: TestClient) -> None:
    answer = client.get("/api/admin/workshops", headers=bearer("organizer-token"))

    assert (answer.status_code, answer.json()) == (200, {"name": "olivia", "roles": ["organizer"]})


def test_a_caller_without_the_role_is_forbidden(client: TestClient) -> None:
    answer = client.get("/api/admin/workshops", headers=bearer("moderator-token"))

    assert (answer.status_code, answer.json()) == (403, {"detail": "Forbidden"})


def test_a_caller_without_roles_is_forbidden(client: TestClient) -> None:
    assert client.get("/api/admin/workshops", headers=bearer("plain-token")).status_code == 403


def test_an_unknown_caller_is_unauthorized_not_forbidden(client: TestClient) -> None:
    assert client.get("/api/admin/workshops", headers=bearer("stolen-token")).status_code == 401
    assert client.get("/api/admin/workshops").status_code == 401


def test_one_of_the_roles_of_an_endpoint_will_do(client: TestClient) -> None:
    assert client.delete("/api/admin/workshops/w1", headers=bearer("moderator-token")).status_code == 204
    assert client.delete("/api/admin/workshops/w1", headers=bearer("organizer-token")).status_code == 204
    assert client.delete("/api/admin/workshops/w1", headers=bearer("plain-token")).status_code == 403


def test_the_caller_is_signed_in_while_the_endpoint_runs(client: TestClient) -> None:
    answer = client.get("/api/admin/workshops/signed-in", headers=bearer("organizer-token"))

    assert answer.json() == {"signed_in": "olivia"}


def test_nobody_is_signed_in_for_a_public_endpoint(client: TestClient) -> None:
    assert client.get("/api/admin/workshops/catalogue").json() == {"signed_in": None}
