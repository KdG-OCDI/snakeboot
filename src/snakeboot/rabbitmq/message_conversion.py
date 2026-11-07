"""JSON bodies to the parameter of a listener, and payloads to JSON bodies: Spring's `Jackson2JsonMessageConverter`."""

import json
from collections.abc import Callable
from typing import get_origin

import pydantic_core
from pydantic import BaseModel, ValidationError

from snakeboot.rabbitmq.rabbit_listener import InvalidRabbitListenerError

type BodyReader = Callable[[bytes], object]


class MessageConversionError(ValueError):
    """A body that cannot become what the listener takes; the message is refused for good."""


def body_reader(parameter_type: object, listener_name: str) -> BodyReader:
    """Returns what turns a body into `parameter_type`: a pydantic model, a `dict` or `bytes`.

    Asked while the application starts, so a listener that takes anything else stops the start-up.
    """
    if parameter_type is bytes:
        return _raw
    if isinstance(parameter_type, type) and issubclass(parameter_type, BaseModel):
        return _model_reader(parameter_type)
    if (get_origin(parameter_type) or parameter_type) is dict:
        return _dictionary
    raise InvalidRabbitListenerError(
        f"{listener_name} takes {parameter_type!r}; a listener takes a pydantic model, a dict or bytes."
    )


def body_of(payload: object) -> bytes:
    """Writes `payload` as JSON: a pydantic model, a dataclass, a dict or a list, datetimes and UUIDs included."""
    return pydantic_core.to_json(payload)


def _raw(body: bytes) -> object:
    return body


def _dictionary(body: bytes) -> object:
    try:
        content = json.loads(body)
    except ValueError as error:
        raise MessageConversionError(f"The body is no JSON: {error}") from error
    if not isinstance(content, dict):
        raise MessageConversionError("The body is JSON, but no object.")
    return content


def _model_reader(model: type[BaseModel]) -> BodyReader:
    def read(body: bytes) -> object:
        try:
            return model.model_validate_json(body)
        except ValidationError as error:
            raise MessageConversionError(f"The body is no {model.__name__}: {error}") from error

    return read
