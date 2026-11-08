"""On Django Ninja, an endpoint that returns ServerSentEvents answers with a stream of text/event-stream."""

import asyncio
from collections.abc import AsyncIterator
from itertools import count
from types import SimpleNamespace
from typing import cast

import pytest
from django.http import StreamingHttpResponse

from snakeboot.component_scan import ComponentScan
from snakeboot.django_ninja import NinjaEndpointFactory, django_blocking, event_stream, rest_api
from snakeboot.rest import ControllerScan
from tests.rest.sample_application import StreamingApplication
from tests.rest.streaming.scoreboard_rest_controller import ScoreboardRestController

_namespaces = count()


def streamed_by_the_view() -> StreamingHttpResponse:
    scanned = ControllerScan(ComponentScan(("tests.rest.streaming",), auto_configuration=())).find()
    view = NinjaEndpointFactory(lambda _: ScoreboardRestController()).create(scanned.endpoints[0])
    return cast("StreamingHttpResponse", view(SimpleNamespace()))


def content_of(response: StreamingHttpResponse) -> str:
    async def receive() -> str:
        parts = cast("AsyncIterator[bytes]", response.streaming_content)
        return b"".join([part async for part in parts]).decode()

    return asyncio.run(receive())


@pytest.fixture(autouse=True)
def no_database(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    journal: list[str] = []
    monkeypatch.setattr(event_stream, "close_old_connections", lambda: journal.append("close old connections"))
    return journal


def test_the_answer_is_an_event_stream_that_nothing_caches_or_buffers() -> None:
    response = streamed_by_the_view()

    assert response.status_code == 200
    assert response["Content-Type"] == "text/event-stream"
    assert (response["Cache-Control"], response["X-Accel-Buffering"]) == ("no-cache", "no")


def test_the_stream_holds_every_change_until_the_value_is_final() -> None:
    assert content_of(streamed_by_the_view()) == (
        'event: score\nid: 1\ndata: {"points":1,"final":false}\n\n'
        'event: score\nid: 2\ndata: {"points":2,"final":false}\n\n'
        'event: score\nid: 3\ndata: {"points":3,"final":true}\n\n'
    )


def test_each_read_of_the_stream_runs_between_fresh_database_connections(no_database: list[str]) -> None:
    def read_the_game() -> int:
        no_database.append("read")
        return 42

    async def read() -> int:
        return await django_blocking(read_the_game)

    assert asyncio.run(read()) == 42
    assert no_database == ["close old connections", "read", "close old connections"]


def test_the_api_publishes_a_streaming_endpoint_without_a_response_model() -> None:
    api = rest_api(StreamingApplication, resolve=lambda _: ScoreboardRestController())
    api.urls_namespace = f"event-stream-test-{next(_namespaces)}"

    operation = api.get_openapi_schema(path_prefix="")["paths"]["/scores/events"]["get"]

    assert list(operation["responses"]) == [200]
    assert "content" not in operation["responses"][200]
