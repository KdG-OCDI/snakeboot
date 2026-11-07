"""The ASGI application answers uvicorn's lifespan with the lifecycle and hands every request to Django's handler."""

import asyncio
from typing import Any

from asgiref.testing import ApplicationCommunicator

from snakeboot.lifecycle import ApplicationLifecycle, LifecycleAsgiApplication
from tests.lifecycle.sample_components import Journal, Recording


class RecordingHandler:
    """Stands in for Django's ASGIHandler: remembers the scopes it was handed."""

    def __init__(self) -> None:
        self.scopes: list[dict[str, Any]] = []

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        self.scopes.append(scope)


def application_with(lifecycle: ApplicationLifecycle, handler: RecordingHandler | None = None) -> Any:
    async def provide() -> ApplicationLifecycle:
        return lifecycle

    return LifecycleAsgiApplication(handler or RecordingHandler(), lifecycle=provide)


async def lifespan(application: Any, *messages: str) -> list[dict[str, Any]]:
    communicator = ApplicationCommunicator(application, {"type": "lifespan"})
    answers = []
    for message in messages:
        await communicator.send_input({"type": message})
        answers.append(await communicator.receive_output(timeout=5))
    await communicator.wait(timeout=5)
    return answers


def test_the_lifecycle_starts_with_the_server_and_stops_with_it() -> None:
    journal = Journal()
    application = application_with(ApplicationLifecycle([Recording(journal, "listener")], on_ready=lambda: None))

    answers = asyncio.run(lifespan(application, "lifespan.startup", "lifespan.shutdown"))

    assert answers == [{"type": "lifespan.startup.complete"}, {"type": "lifespan.shutdown.complete"}]
    assert journal.entries == ["start listener", "stop listener"]


def test_a_start_up_that_fails_tells_the_server_so_it_stops() -> None:
    journal = Journal()
    broken = ApplicationLifecycle([Recording(journal, "broken", failing="start")], on_ready=lambda: None)

    answers = asyncio.run(lifespan(application_with(broken), "lifespan.startup"))

    assert answers == [{"type": "lifespan.startup.failed", "message": "RuntimeError: broken cannot start"}]


def test_every_other_scope_goes_to_the_handler_unchanged() -> None:
    handler = RecordingHandler()
    application = application_with(ApplicationLifecycle([], on_ready=lambda: None), handler)
    scope = {"type": "http", "path": "/health"}

    asyncio.run(ApplicationCommunicator(application, scope).wait(timeout=5))

    assert handler.scopes == [scope]
