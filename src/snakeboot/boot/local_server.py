import threading
import time
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from httpx2 import Client

type ServerClient = Client
"""A client of a `LocalServer` over the network: `get`, `post`, `put`, `patch` and `delete`, like `RestClient`."""

LOOPBACK: Final = "127.0.0.1"
"""Where a `LocalServer` listens: this machine only."""

START_SECONDS: Final = 10.0
"""How long a `LocalServer` may take to start, or to stop, before the test fails instead of hanging."""


class LocalServerError(RuntimeError):
    """Raised when the server of a test did not start, or did not stop, in time."""


class LocalServer:
    """The application of a test served over HTTP on a free port, like `@SpringBootTest(webEnvironment = RANDOM_PORT)`.

        @application_test
        def test_a_page_of_another_origin_may_call_the_api(server: Autowired[LocalServer]) -> None:
            with server.client() as client:                              # over the network, like TestRestTemplate
                response = client.options("/api/auctions", headers={"Origin": "https://shop.example", ...})

    uvicorn serves the application on a thread of its own, at `url` (`port` is `@LocalServerPort`), with the
    lifecycle running, as `serve` would: what the client in the test's process cannot show, such as a browser, CORS
    or a stream of server-sent events as it arrives, can be tested here. It accepts calls to `127.0.0.1` besides
    `[server] allowed_hosts`. The application of the test stops it when it closes.
    """

    def __init__(self, server: Any, thread: threading.Thread) -> None:
        self._server = server
        self._thread = thread
        self.port: int = server.servers[0].sockets[0].getsockname()[1]

    @classmethod
    def start(cls, application: Any) -> "LocalServer":
        """Starts serving the ASGI `application` on a free port of this machine, and returns once it listens."""
        import uvicorn  # noqa: PLC0415  # reason: only a test that asks for a server loads it

        server = uvicorn.Server(uvicorn.Config(application, host=LOOPBACK, port=0, log_config=None, lifespan="on"))
        thread = threading.Thread(target=server.run, name="snakeboot-local-server", daemon=True)
        thread.start()
        deadline = time.monotonic() + START_SECONDS
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise LocalServerError(f"The server of the test did not start within {START_SECONDS} seconds.")
            time.sleep(0.01)
        return cls(server, thread)

    @property
    def url(self) -> str:
        """Where the server listens: `http://127.0.0.1:<port>`."""
        return f"http://{LOOPBACK}:{self.port}"

    def client(self) -> ServerClient:
        """Returns a client that calls the server over the network; use it as a context manager to close it."""
        from httpx2 import Client  # noqa: PLC0415  # reason: snakeboot[testing] brings it, a server needs it

        return Client(base_url=self.url)

    def stop(self) -> None:
        """Stops the server, after the calls in hand, and the lifecycle with it."""
        self._server.should_exit = True
        self._thread.join(timeout=START_SECONDS)
        if self._thread.is_alive():
            raise LocalServerError(f"The server of the test did not stop within {START_SECONDS} seconds.")
