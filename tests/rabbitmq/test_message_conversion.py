"""A body becomes the pydantic model, dict or bytes a listener takes, and a payload becomes JSON."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from pydantic import BaseModel

from snakeboot.rabbitmq import InvalidRabbitListenerError, MessageConversionError
from snakeboot.rabbitmq.message_conversion import body_of, body_reader


class Greeting(BaseModel):
    """Stands in for a message."""

    text: str


def test_a_body_becomes_a_pydantic_model() -> None:
    assert body_reader(Greeting, "listener")(b'{"text": "hello"}') == Greeting(text="hello")


@pytest.mark.parametrize("parameter_type", [dict, dict[str, Any]])
def test_a_body_becomes_a_dict(parameter_type: object) -> None:
    assert body_reader(parameter_type, "listener")(b'{"text": "hello"}') == {"text": "hello"}


def test_bytes_are_handed_over_as_they_came() -> None:
    assert body_reader(bytes, "listener")(b"\x00raw") == b"\x00raw"


@pytest.mark.parametrize(
    ("parameter_type", "body"),
    [(Greeting, b'{"txt": "hello"}'), (dict, b"[1, 2]"), (dict, b"not json")],
)
def test_a_body_that_does_not_fit_is_a_conversion_error(parameter_type: object, body: bytes) -> None:
    with pytest.raises(MessageConversionError):
        body_reader(parameter_type, "listener")(body)


def test_a_listener_that_takes_another_type_stops_the_start_up() -> None:
    with pytest.raises(InvalidRabbitListenerError, match=r"Listener.on_message takes"):
        body_reader(str, "Listener.on_message")


def test_a_payload_becomes_json_with_datetimes_and_uuids() -> None:
    payload = {
        "greeting": Greeting(text="hello"),
        "at": datetime(2026, 11, 7, tzinfo=UTC),
        "id": UUID("a0000000-0000-4000-8000-000000000001"),
    }

    assert json.loads(body_of(payload)) == {
        "greeting": {"text": "hello"},
        "at": "2026-11-07T00:00:00Z",
        "id": "a0000000-0000-4000-8000-000000000001",
    }
