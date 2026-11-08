"""On FastAPI, an endpoint that returns ServerSentEvents answers with a stream of text/event-stream."""

import pytest
from fastapi.testclient import TestClient

from snakeboot.fastapi_web import rest_api
from tests.rest.sample_application import StreamingApplication
from tests.rest.streaming.scoreboard_rest_controller import ScoreboardRestController


@pytest.fixture
def client() -> TestClient:
    return TestClient(rest_api(StreamingApplication, lambda _: ScoreboardRestController()))


def test_the_answer_is_an_event_stream_that_nothing_caches_or_buffers(client: TestClient) -> None:
    response = client.get("/api/scores/events")

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/event-stream")
    assert (response.headers["Cache-Control"], response.headers["X-Accel-Buffering"]) == ("no-cache", "no")


def test_the_stream_holds_every_change_until_the_value_is_final(client: TestClient) -> None:
    assert client.get("/api/scores/events").text == (
        'event: score\nid: 1\ndata: {"points":1,"final":false}\n\n'
        'event: score\nid: 2\ndata: {"points":2,"final":false}\n\n'
        'event: score\nid: 3\ndata: {"points":3,"final":true}\n\n'
    )


def test_the_openapi_document_names_the_event_stream_without_a_model(client: TestClient) -> None:
    operation = client.get("/api/openapi.json").json()["paths"]["/api/scores/events"]["get"]

    assert list(operation["responses"]) == ["200"]
    assert list(operation["responses"]["200"]["content"]) == ["text/event-stream"]
