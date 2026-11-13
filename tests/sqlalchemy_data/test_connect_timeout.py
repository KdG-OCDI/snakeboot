"""A PostgreSQL server that does not answer stops the connection after a while, instead of letting it wait for good."""

import socket
import threading
import time
from collections.abc import Iterator

import pytest
from sqlalchemy.exc import OperationalError

import snakeboot.sqlalchemy_data.database as database_module
from snakeboot.configuration import DatabaseProperties
from snakeboot.sqlalchemy_data import Database

GUARD_SECONDS = 20
"""Stops the test, should the connection wait for good after all."""


@pytest.fixture
def silent_server() -> Iterator[int]:
    """A port that accepts connections and never answers them: a server that hangs, or a refused connection on
    Windows, as psycopg sees them."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        yield listener.getsockname()[1]


def test_connecting_to_a_server_that_does_not_answer_gives_up_after_the_connect_timeout(
    silent_server: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(database_module, "CONNECT_TIMEOUT_SECONDS", 2)
    server = DatabaseProperties.model_validate(
        {"host": "127.0.0.1", "port": silent_server, "name": "shop", "user": "shop", "password": "secret"}
    )
    engine = Database.of(server).engine
    errors: list[Exception] = []

    def connect() -> None:
        try:
            engine.connect().close()
        except OperationalError as error:
            errors.append(error)

    started = time.monotonic()
    attempt = threading.Thread(target=connect, daemon=True)
    attempt.start()
    attempt.join(GUARD_SECONDS)

    assert not attempt.is_alive(), f"still connecting after {GUARD_SECONDS} seconds"
    assert len(errors) == 1
    assert "timeout" in str(errors[0])
    assert time.monotonic() - started < GUARD_SECONDS
    engine.dispose()
