"""A service whose deployment sets its secrets as environment variables: its files leave them out."""

from snakeboot.component_scan import application_root
from snakeboot.configuration import Section, configuration_properties


@application_root
class ServiceWithoutSecretsApplication:
    pass


@configuration_properties("mail")
class MailProperties(Section):
    """A section of the application itself, read when the container is built."""

    server: str
    sender: str
