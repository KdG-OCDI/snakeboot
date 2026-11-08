"""`snakeboot.boot` starts an application: its commands with `run`, its server with `asgi_application`."""

from fastapi.testclient import TestClient

from snakeboot import boot
from snakeboot.lifecycle import LifecycleAsgiApplication
from tests.application.sample_service.sample_service_application import SampleServiceApplication


def test_it_offers_the_entry_points_and_the_bindings_it_chooses() -> None:
    assert sorted(boot.__all__) == ["CONDITIONAL_MODULES", "application_from_environment", "asgi_application", "run"]


def test_asgi_application_serves_the_api_with_the_lifecycle_around_it() -> None:
    application = boot.asgi_application(SampleServiceApplication)

    with TestClient(application) as client:
        assert client.get("/health").json() == {"status": "ok", "service": "sample_service"}
        assert client.get("/api/openapi.json").json()["info"]["title"] == "Sample service"
    assert isinstance(application, LifecycleAsgiApplication)
