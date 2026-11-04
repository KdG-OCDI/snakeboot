from snakeboot.configuration import Section, configuration_properties


@configuration_properties("greeting")
class GreetingProperties(Section):
    """The section [greeting] of the services under test."""

    text: str
