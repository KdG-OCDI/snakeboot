from typing import Annotated, Literal

from pydantic import Field

from snakeboot.configuration import Section, configuration_properties


class SenderProperties(Section):
    name: str
    address: str


class EmailChannel(Section):
    kind: Literal["email"]
    server: str


class LogChannel(Section):
    """A variant without keys of its own: the one to put in application.toml when another may replace it."""

    kind: Literal["log"]


@configuration_properties("greeting")
class GreetingProperties(Section):
    text: str
    repeat: int
    sender: SenderProperties
    channel: Annotated[LogChannel | EmailChannel, Field(discriminator="kind")]


@configuration_properties("farewell")
class FarewellProperties(Section):
    """A section application.toml does not have."""

    text: str
