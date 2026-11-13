"""Log lines are plain text, or JSON in the Elastic Common Schema; both carry the trace id of the work in hand."""

import io
import json
import logging
from collections.abc import Iterator

import pytest

from snakeboot.application.logging_configuration import configure_logging
from snakeboot.configuration import LoggingProperties, ServerProperties
from snakeboot.tracing import TraceContext

SERVER = ServerProperties(
    host="127.0.0.1", port=8000, workers=1, debug=False, allowed_hosts=("*",), log_level="INFO", max_upload_size=None
)
CALLER = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


@pytest.fixture
def console() -> Iterator[io.StringIO]:
    written = io.StringIO()
    yield written
    logging.getLogger().handlers.clear()


def configured(console: io.StringIO, logging_properties: LoggingProperties | None) -> logging.Logger:
    configure_logging(SERVER, logging_properties, service="tictactoe")
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    handler.setStream(console)
    return logging.getLogger("tictactoe.games")


def test_a_plain_line_carries_the_trace_id_of_the_work_in_hand(console: io.StringIO) -> None:
    logger = configured(console, None)

    logger.info("outside")
    with TraceContext.started(CALLER):
        logger.info("inside")

    outside, inside = console.getvalue().splitlines()
    assert outside.endswith(" INFO tictactoe.games: outside")
    assert inside.endswith(" INFO [4bf92f3577b34da6a3ce929d0e0e4736] tictactoe.games: inside")


def test_an_ecs_line_is_one_json_object_with_fields_of_its_own(console: io.StringIO) -> None:
    logger = configured(console, LoggingProperties(format="ecs"))

    with TraceContext.started(CALLER) as span:
        logger.warning("Game %s took too long", "g1")

    line = json.loads(console.getvalue())
    assert line["message"] == "Game g1 took too long"
    assert line["log"] == {"level": "WARNING", "logger": "tictactoe.games"}
    assert line["service"] == {"name": "tictactoe"}
    assert line["trace"] == {"id": "4bf92f3577b34da6a3ce929d0e0e4736"}
    assert line["span"] == {"id": span.span_id}
    assert line["@timestamp"].endswith("+00:00")


def test_an_ecs_line_holds_the_error_and_its_stack_trace(console: io.StringIO) -> None:
    logger = configured(console, LoggingProperties(format="ecs"))

    try:
        raise ValueError("no such cell")
    except ValueError:
        logger.exception("A move failed")

    line = json.loads(console.getvalue())
    assert line["error"]["type"] == "ValueError"
    assert line["error"]["message"] == "no such cell"
    assert "Traceback" in line["error"]["stack_trace"]
    assert "trace" not in line
