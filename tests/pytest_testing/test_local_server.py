"""`Autowired[LocalServer]` serves the application of a test over HTTP on a free port, like `RANDOM_PORT`."""

import httpx2
import pytest

from snakeboot.boot.testing import LocalServer, TestApplication
from snakeboot.testing import Autowired, application_test, eventually, signed_in_as
from tests.pytest_testing.notebook.notebook_application import NotebookApplication
from tests.pytest_testing.notebook.notes import WriteNote

notebook_test = application_test(application=NotebookApplication)

AS_A_WRITER = signed_in_as("ann", roles={"writer"})


@notebook_test
def test_the_application_is_served_over_http_on_a_free_port(server: Autowired[LocalServer]) -> None:
    with server.client() as client:
        missing = client.get("/api/notes/last")
        created = client.post("/api/notes", json={"text": "hello"}, headers=AS_A_WRITER)

    assert (missing.status_code, created.status_code) == (404, 201)
    assert server.url == f"http://127.0.0.1:{server.port}"


@notebook_test
def test_the_server_and_the_test_share_one_application(
    server: Autowired[LocalServer], write_note: Autowired[WriteNote]
) -> None:
    write_note.execute("hi", "ann")

    with server.client() as client:
        assert client.get("/api/notes/last").json()["text"] == "hi"


@notebook_test
def test_a_check_waits_for_what_a_call_of_another_thread_did(server: Autowired[LocalServer]) -> None:
    with server.client() as client:
        client.post("/api/notes", json={"text": "later"}, headers=AS_A_WRITER)

        assert eventually(lambda: client.get("/api/notes/last").json()["text"]) == "later"


def test_closing_the_application_stops_its_server() -> None:
    with TestApplication.start(NotebookApplication) as application:
        url = application.local_server().url
        assert httpx2.get(f"{url}/health/liveness").status_code == 200

    with pytest.raises(httpx2.ConnectError):
        httpx2.get(f"{url}/health/liveness")
