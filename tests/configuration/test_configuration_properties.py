"""`@configuration_properties` and the rules a section follows, checked when the configuration is loaded."""

import pytest
from pydantic import BaseModel, ConfigDict, Field

from snakeboot.configuration import InvalidConfigurationPropertiesError, configuration_properties, load_configuration
from tests.configuration.sample_service.greeting_properties import GreetingProperties

SAMPLE = "tests.configuration.sample_service"


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str


@pytest.mark.parametrize("prefix", ["Greeting", "greeting.sender", "greeting__sender", "_greeting", "greeting_", ""])
def test_a_prefix_is_one_lowercase_name_with_single_underscores(prefix: str) -> None:
    with pytest.raises(InvalidConfigurationPropertiesError, match="one lowercase name"):
        configuration_properties(prefix)


def test_a_prefix_may_contain_single_underscores_and_digits() -> None:
    @configuration_properties("data_service2")
    class DataServiceProperties(Closed):
        pass

    assert DataServiceProperties.__name__ == "DataServiceProperties"


def test_only_a_pydantic_model_can_be_a_section() -> None:
    class PlainClass:
        pass

    with pytest.raises(InvalidConfigurationPropertiesError, match="marks a Pydantic model"):
        configuration_properties("plain")(PlainClass)  # type: ignore[type-var]  # the point: not a model


def test_an_unmarked_model_is_not_a_section() -> None:
    with pytest.raises(InvalidConfigurationPropertiesError, match="Closed is not marked"):
        load_configuration(Closed, package=SAMPLE)


def test_a_subclass_does_not_inherit_the_section() -> None:
    class SpecialGreeting(GreetingProperties):
        pass

    with pytest.raises(InvalidConfigurationPropertiesError, match="SpecialGreeting is not marked"):
        load_configuration(SpecialGreeting, package=SAMPLE)


def test_two_models_cannot_claim_the_same_section() -> None:
    @configuration_properties("greeting")
    class OtherGreeting(Closed):
        pass

    with pytest.raises(InvalidConfigurationPropertiesError, match=r"both claim the section \[greeting\]"):
        load_configuration(GreetingProperties, OtherGreeting, package=SAMPLE)


def test_a_default_in_code_is_refused() -> None:
    @configuration_properties("greeting")
    class GreetingWithDefault(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        text: str = "Hello"

    with pytest.raises(InvalidConfigurationPropertiesError, match=r"GreetingWithDefault\.text has a default"):
        load_configuration(GreetingWithDefault, package=SAMPLE)


def test_a_default_factory_is_a_default_too() -> None:
    @configuration_properties("greeting")
    class GreetingWithFactory(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        hosts: list[str] = Field(default_factory=list)

    with pytest.raises(InvalidConfigurationPropertiesError, match=r"GreetingWithFactory\.hosts has a default"):
        load_configuration(GreetingWithFactory, package=SAMPLE)


def test_a_default_in_a_nested_model_is_refused() -> None:
    class SenderWithDefault(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        name: str = "snakeboot"

    @configuration_properties("greeting")
    class GreetingWithNestedDefault(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        senders: tuple[SenderWithDefault, ...]

    with pytest.raises(InvalidConfigurationPropertiesError, match=r"SenderWithDefault\.name has a default"):
        load_configuration(GreetingWithNestedDefault, package=SAMPLE)


def test_a_model_that_ignores_unknown_keys_is_refused() -> None:
    @configuration_properties("greeting")
    class LenientGreeting(BaseModel):
        model_config = ConfigDict(frozen=True)

        text: str

    with pytest.raises(InvalidConfigurationPropertiesError, match="LenientGreeting must declare"):
        load_configuration(LenientGreeting, package=SAMPLE)


def test_a_mutable_model_is_refused() -> None:
    @configuration_properties("greeting")
    class MutableGreeting(BaseModel):
        model_config = ConfigDict(extra="forbid")

        text: str

    with pytest.raises(InvalidConfigurationPropertiesError, match="MutableGreeting must declare"):
        load_configuration(MutableGreeting, package=SAMPLE)


def test_an_open_model_inside_a_union_is_refused() -> None:
    class OpenChannel(BaseModel):
        kind: str

    @configuration_properties("greeting")
    class GreetingWithOpenChannel(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        channel: Closed | OpenChannel

    with pytest.raises(InvalidConfigurationPropertiesError, match="OpenChannel must declare"):
        load_configuration(GreetingWithOpenChannel, package=SAMPLE)
