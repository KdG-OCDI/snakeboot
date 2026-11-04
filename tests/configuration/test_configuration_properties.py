"""`@configuration_properties` and the rules a section follows, checked when the configuration is loaded."""

import pytest
from pydantic import BaseModel, ConfigDict, Field

from snakeboot.configuration import (
    InvalidConfigurationPropertiesError,
    Section,
    configuration_properties,
    load_configuration,
)
from tests.configuration.sample_service.greeting_properties import GreetingProperties

SAMPLE = "tests.configuration.sample_service"


class Closed(Section):
    value: str


class Lookalike(BaseModel):
    """Configured like a Section, but not one: the contract is the base class."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str


class PlainClass:
    pass


@pytest.mark.parametrize("prefix", ["Greeting", "greeting.sender", "greeting__sender", "_greeting", "greeting_", ""])
def test_a_prefix_is_one_lowercase_name_with_single_underscores(prefix: str) -> None:
    with pytest.raises(InvalidConfigurationPropertiesError, match="one lowercase name"):
        configuration_properties(prefix)


def test_a_prefix_may_contain_single_underscores_and_digits() -> None:
    @configuration_properties("data_service2")
    class DataServiceProperties(Closed):
        pass

    assert DataServiceProperties.__name__ == "DataServiceProperties"


def test_only_a_section_can_be_marked() -> None:
    mark = configuration_properties("plain")

    with pytest.raises(InvalidConfigurationPropertiesError, match=r"extends Section, not <class .*PlainClass"):
        mark(PlainClass)  # type: ignore[type-var]  # the point: not a model
    with pytest.raises(InvalidConfigurationPropertiesError, match=r"extends Section, not <class .*Lookalike"):
        mark(Lookalike)  # type: ignore[type-var]  # the point: a model, but not a Section


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


def test_a_nested_model_must_extend_section_even_when_configured_like_one() -> None:
    @configuration_properties("greeting")
    class GreetingWithLookalike(Section):
        sender: Lookalike

    with pytest.raises(InvalidConfigurationPropertiesError, match="Lookalike must extend Section"):
        load_configuration(GreetingWithLookalike, package=SAMPLE)


def test_an_open_model_inside_a_union_is_refused() -> None:
    class OpenChannel(BaseModel):
        kind: str

    @configuration_properties("greeting")
    class GreetingWithOpenChannel(Section):
        channel: Closed | OpenChannel

    with pytest.raises(InvalidConfigurationPropertiesError, match="OpenChannel must extend Section"):
        load_configuration(GreetingWithOpenChannel, package=SAMPLE)


def test_a_section_that_ignores_unknown_keys_is_refused() -> None:
    @configuration_properties("greeting")
    class LenientGreeting(Section):
        model_config = ConfigDict(extra="ignore")

        text: str

    with pytest.raises(InvalidConfigurationPropertiesError, match="LenientGreeting changes the model_config"):
        load_configuration(LenientGreeting, package=SAMPLE)


def test_a_mutable_section_is_refused() -> None:
    class MutableSender(Section):
        model_config = ConfigDict(frozen=False)

        name: str

    @configuration_properties("greeting")
    class GreetingWithMutableSender(Section):
        sender: MutableSender

    with pytest.raises(InvalidConfigurationPropertiesError, match="MutableSender changes the model_config"):
        load_configuration(GreetingWithMutableSender, package=SAMPLE)


def test_a_default_in_code_is_refused() -> None:
    @configuration_properties("greeting")
    class GreetingWithDefault(Section):
        text: str = "Hello"

    with pytest.raises(InvalidConfigurationPropertiesError, match=r"GreetingWithDefault\.text has a default"):
        load_configuration(GreetingWithDefault, package=SAMPLE)


def test_a_default_factory_is_a_default_too() -> None:
    @configuration_properties("greeting")
    class GreetingWithFactory(Section):
        hosts: list[str] = Field(default_factory=list)

    with pytest.raises(InvalidConfigurationPropertiesError, match=r"GreetingWithFactory\.hosts has a default"):
        load_configuration(GreetingWithFactory, package=SAMPLE)


def test_a_default_in_a_nested_model_is_refused() -> None:
    class SenderWithDefault(Section):
        name: str = "snakeboot"

    @configuration_properties("greeting")
    class GreetingWithNestedDefault(Section):
        senders: tuple[SenderWithDefault, ...]

    with pytest.raises(InvalidConfigurationPropertiesError, match=r"SenderWithDefault\.name has a default"):
        load_configuration(GreetingWithNestedDefault, package=SAMPLE)
