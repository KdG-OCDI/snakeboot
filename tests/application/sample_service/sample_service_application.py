"""A service with a database, a REST API and a command, as an application of snakeboot writes one."""

from snakeboot.component_scan import application_root
from snakeboot.openapi import openapi_definition


@openapi_definition(title="Sample service", version="1.0.0")
@application_root
class SampleServiceApplication:
    pass


@application_root(base_packages=("tests.command_line.clashing_commands",))
class ClashingCommandsServiceApplication:
    """A service with a database whose own command is named like snakeboot's `migrate`."""
