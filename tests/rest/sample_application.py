"""An application whose container holds the sample controllers."""

from snakeboot.component_scan import application_root
from snakeboot.openapi import openapi_definition


@openapi_definition(title="Greetings", version="2.1.0", description="Says hello and goodbye.")
@application_root(base_packages=("tests.rest.sample_controllers",))
class GreetingApplication:
    pass


@application_root(base_packages=("tests.rest.sample_controllers",))
class UndescribedApplication:
    pass


@application_root(base_packages=("tests.rest.sample_controllers", "tests.rest.secured"))
class SecuredApplication:
    pass


@application_root(base_packages=("tests.rest.sample_controllers", "tests.rest.doubly_secured"))
class DoublySecuredApplication:
    pass
