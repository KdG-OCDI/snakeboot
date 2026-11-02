from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from snakeboot.configuration import configuration_properties


class SenderProperties(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    address: str


class EmailChannel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["email"]
    server: str


class LogChannel(BaseModel):
    """A variant without keys of its own: the one to put in application.toml when another may replace it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["log"]


@configuration_properties("greeting")
class GreetingProperties(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    repeat: int
    sender: SenderProperties
    channel: Annotated[LogChannel | EmailChannel, Field(discriminator="kind")]


@configuration_properties("farewell")
class FarewellProperties(BaseModel):
    """A section application.toml does not have."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
