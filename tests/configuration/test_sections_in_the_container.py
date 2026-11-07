"""A section is a component of the module that declares it: it enters the container with that module."""

import sys

import pytest
import wireup
from wireup import injectable

from snakeboot.configuration import (
    CONFIGURATION_KEY,
    Configuration,
    ServerProperties,
    begin_configuration,
    load_configuration,
    sections_declared_in,
)
from tests.configuration.sample_service import greeting_properties
from tests.configuration.sample_service.greeting_properties import FarewellProperties, GreetingProperties

SAMPLE = "tests.configuration.sample_service"


@injectable
class Greeter:
    def __init__(self, properties: GreetingProperties) -> None:
        self.properties = properties

    def greet(self) -> str:
        return " ".join([self.properties.text] * self.properties.repeat)


@pytest.fixture
def configuration() -> Configuration:
    return load_configuration(ServerProperties, GreetingProperties, package=SAMPLE)


def container_with(configuration: Configuration) -> wireup.SyncContainer:
    # What a Django application does: the module of the section is scanned, the configuration is in the config.
    return wireup.create_sync_container(
        injectables=[greeting_properties, Greeter], config={CONFIGURATION_KEY: configuration}
    )


def test_a_component_receives_its_section_by_type(configuration: Configuration) -> None:
    assert container_with(configuration).get(Greeter).greet() == "Hello"


def test_the_container_hands_out_the_object_that_was_read(configuration: Configuration) -> None:
    assert container_with(configuration).get(GreetingProperties) is configuration.get(GreetingProperties)


def test_the_provider_of_a_section_is_a_member_of_its_module() -> None:
    assert callable(getattr(greeting_properties, "provide_greeting_properties", None))
    assert callable(getattr(greeting_properties, "provide_farewell_properties", None))


def test_a_section_that_was_not_read_is_not_there(configuration: Configuration) -> None:
    with pytest.raises(LookupError, match="FarewellProperties is not a section of this configuration"):
        configuration.get(FarewellProperties)


def test_a_section_asked_for_before_the_second_step_is_not_read_yet() -> None:
    configuration = begin_configuration(ServerProperties, package=SAMPLE)

    with pytest.raises(LookupError, match="GreetingProperties is not read yet"):
        container_with(configuration).get(GreetingProperties)


def test_a_module_declares_the_sections_marked_in_it_in_the_order_of_the_file() -> None:
    # SenderProperties and the channels are tables nested in a section, not sections themselves.
    assert sections_declared_in(greeting_properties) == [GreetingProperties, FarewellProperties]


def test_a_section_imported_from_another_module_is_not_declared_here() -> None:
    assert sections_declared_in(sys.modules[__name__]) == []
