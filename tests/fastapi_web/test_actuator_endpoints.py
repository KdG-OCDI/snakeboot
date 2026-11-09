"""Beside the API, the server answers its health and its metrics, runs every call in a span and times it."""

from typing import override

import pytest
import wireup
from fastapi.testclient import TestClient

from snakeboot.actuator import Actuator, ApplicationHealth, HealthIndicator, MeterRegistry
from snakeboot.configuration import CorsProperties
from snakeboot.fastapi_web import rest_api
from tests.rest.sample_application import SecuredApplication, TracedApplication
from tests.rest.sample_controllers.greeting_rest_controller import Greeter, GreetingRestController
from tests.rest.secured import token_checker
from tests.rest.secured.who_am_i_rest_controller import WhoAmIRestController
from tests.rest.traced.trace_rest_controller import TraceRestController

CALLER = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


class BrokerHealthIndicator(HealthIndicator, component=False):
    def __init__(self, *, up: bool) -> None:
        self.up = up

    @override
    def check(self) -> None:
        if not self.up:
            raise ConnectionError("down")


def client_of(actuator: Actuator, cors: CorsProperties | None = None) -> TestClient:
    container = wireup.create_sync_container(
        injectables=[
            GreetingRestController,
            WhoAmIRestController,
            token_checker,
            wireup.instance(Greeter(), as_type=Greeter),
        ]
    )
    return TestClient(rest_api(SecuredApplication, container.get, cors=cors, actuator=actuator))


@pytest.fixture
def meters() -> MeterRegistry:
    return MeterRegistry()


def test_health_names_every_part_and_answers_503_when_one_is_down(meters: MeterRegistry) -> None:
    client = client_of(Actuator(ApplicationHealth([BrokerHealthIndicator(up=False)]), meters))

    answer = client.get("/health")

    assert answer.status_code == 503
    assert answer.json() == {"status": "DOWN", "service": "rest", "components": {"broker": {"status": "DOWN"}}}
    assert client.get("/health/readiness").status_code == 503


def test_liveness_is_up_whatever_the_parts_say(meters: MeterRegistry) -> None:
    client = client_of(Actuator(ApplicationHealth([BrokerHealthIndicator(up=False)]), meters))

    answer = client.get("/health/liveness")

    assert (answer.status_code, answer.json()) == (200, {"status": "UP"})


def test_the_probes_answer_without_a_token_and_stay_out_of_the_openapi_document(meters: MeterRegistry) -> None:
    client = client_of(Actuator(ApplicationHealth([BrokerHealthIndicator(up=True)]), meters))

    assert client.get("/health").status_code == 200
    assert client.get("/metrics").status_code == 200
    assert not {"/health", "/health/liveness", "/metrics"} & set(client.get("/api/openapi.json").json()["paths"])


def test_every_call_is_timed_by_its_route_template(meters: MeterRegistry) -> None:
    client = client_of(Actuator(meters=meters))
    client.get("/api/me", headers={"Authorization": "Bearer good-token"})
    client.get("/api/me")
    client.get("/nowhere")

    scraped = client.get("/metrics")

    assert scraped.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"
    assert 'http_server_requests_seconds_count{method="GET",status="200",uri="/api/me"} 1.0' in scraped.text
    assert 'http_server_requests_seconds_count{method="GET",status="401",uri="/api/me"} 1.0' in scraped.text
    assert 'http_server_requests_seconds_count{method="GET",status="404",uri="NOT_FOUND"} 1.0' in scraped.text


def test_a_call_runs_in_a_span_of_the_caller_s_trace() -> None:
    client = TestClient(rest_api(TracedApplication, lambda _: TraceRestController()))

    continued = client.get("/api/trace", headers={"traceparent": CALLER}).json()["trace_id"]
    started = client.get("/api/trace").json()["trace_id"]

    assert continued == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert started is not None
    assert started != continued


def test_cors_lets_the_pages_of_the_allowed_origins_call_the_api(meters: MeterRegistry) -> None:
    cors = CorsProperties(
        allowed_origins=("https://games.example.com",),
        allowed_methods=("GET", "POST"),
        allowed_headers=("Authorization",),
        allow_credentials=False,
    )
    client = client_of(Actuator(meters=meters), cors)
    asking = {"Origin": "https://games.example.com", "Access-Control-Request-Method": "GET"}

    allowed = client.options("/api/me/door", headers=asking)
    refused = client.options("/api/me/door", headers={**asking, "Origin": "https://evil.example.com"})

    assert allowed.headers["access-control-allow-origin"] == "https://games.example.com"
    assert "access-control-allow-origin" not in refused.headers


def test_cors_refuses_any_origin_with_credentials() -> None:
    with pytest.raises(ValueError, match="allowed_origins cannot hold"):
        CorsProperties(allowed_origins=("*",), allowed_methods=("GET",), allowed_headers=(), allow_credentials=True)
