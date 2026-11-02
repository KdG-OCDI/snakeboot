"""Every section reaches wireup by its type, like a `@ConfigurationProperties` bean."""

import pytest
import wireup
from ninja import NinjaAPI
from wireup import injectable

from snakeboot.configuration import Configuration, DjangoProperties, load_configuration
from snakeboot.rest import RestControllerMounter
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
    return load_configuration(DjangoProperties, GreetingProperties, package=SAMPLE)


def test_a_component_receives_its_section_by_type(configuration: Configuration) -> None:
    container = wireup.create_sync_container(injectables=[*configuration.injectables(), Greeter])

    assert container.get(Greeter).greet() == "Hello"


def test_the_container_hands_out_the_loaded_objects(configuration: Configuration) -> None:
    container = wireup.create_sync_container(injectables=configuration.injectables())

    assert container.get(GreetingProperties) is configuration.get(GreetingProperties)
    assert container.get(DjangoProperties) is configuration.get(DjangoProperties)


def test_a_section_that_was_not_loaded_is_not_there(configuration: Configuration) -> None:
    with pytest.raises(LookupError, match="FarewellProperties is not a section of this configuration"):
        configuration.get(FarewellProperties)


def test_the_rest_scan_passes_the_module_of_the_sections_by(configuration: Configuration) -> None:
    # settings.WIREUP.injectables holds this module next to the scanned packages; the mounter scans that same list.
    api = NinjaAPI(urls_namespace="configuration-test")

    assert RestControllerMounter().mount(api, scan=configuration.injectables()).controllers == []
