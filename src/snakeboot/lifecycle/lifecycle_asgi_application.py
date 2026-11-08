import asyncio
import logging
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any, Protocol

from snakeboot.lifecycle.application_lifecycle import ApplicationLifecycle

logger = logging.getLogger(__name__)

type Message = MutableMapping[str, Any]
type Receive = Callable[[], Awaitable[Message]]
type Send = Callable[[Message], Awaitable[None]]


class AsgiApplication(Protocol):
    """Anything an ASGI server can call, such as a FastAPI application."""

    def __call__(self, scope: Any, receive: Any, send: Any) -> Awaitable[None]:
        """Handles one connection."""


class LifecycleAsgiApplication:
    """An ASGI application that starts the application's lifecycle with the server and stops it with the server.

    The application knows no moment "the server starts"; the ASGI server does, and says so with the `lifespan`
    scope. This application answers that scope itself and hands every other one to the handler
    unchanged. The lifecycle starts on a thread, as it may block (opening connections, registering with a platform);
    a failure answers `lifespan.startup.failed`, so the server stops instead of serving a half-started application.
    """

    def __init__(self, handler: AsgiApplication, lifecycle: Callable[[], Awaitable[ApplicationLifecycle]]) -> None:
        self.handler = handler
        self._lifecycle = lifecycle

    async def __call__(self, scope: Any, receive: Receive, send: Send) -> None:
        """Answers `lifespan` itself; hands `http` and anything else to the handler."""
        if scope["type"] != "lifespan":
            await self.handler(scope, receive, send)
            return
        lifecycle: ApplicationLifecycle | None = None
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                lifecycle = await self._started(send)
                if lifecycle is None:
                    return
            elif message["type"] == "lifespan.shutdown":
                if lifecycle is not None:
                    await asyncio.to_thread(lifecycle.stop)
                await send({"type": "lifespan.shutdown.complete"})
                return

    async def _started(self, send: Send) -> ApplicationLifecycle | None:
        try:
            lifecycle = await self._lifecycle()
            await asyncio.to_thread(lifecycle.start)
        except Exception as error:
            logger.exception("The application did not start")
            await send({"type": "lifespan.startup.failed", "message": f"{type(error).__name__}: {error}"})
            return None
        await send({"type": "lifespan.startup.complete"})
        return lifecycle
