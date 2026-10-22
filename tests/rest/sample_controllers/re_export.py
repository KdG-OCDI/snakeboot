"""Imports a controller defined elsewhere; the scanner must not report it twice."""

from tests.rest.sample_controllers.greeting_rest_controller import GreetingRestController

__all__ = ["GreetingRestController"]
