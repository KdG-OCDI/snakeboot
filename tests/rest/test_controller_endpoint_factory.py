"""The endpoint factory hides `self` from Ninja and calls the method on the resolved controller."""

import inspect

import pytest

from snakeboot.rest import ControllerEndpointFactory, InvalidRestControllerError
from tests.rest.sample_controllers.greeting_rest_controller import Greeter, GreetingRestController


def test_shows_ninja_the_signature_without_self() -> None:
    endpoint = ControllerEndpointFactory(lambda _: None).create(GreetingRestController, GreetingRestController.greet)

    assert list(inspect.signature(endpoint).parameters) == ["request", "name"]
    assert endpoint.__name__ == "greet"


def test_calls_the_method_on_the_controller_the_resolver_returns() -> None:
    controller = GreetingRestController(Greeter())
    resolved: list[type] = []

    def resolve(controller_class: type) -> object:
        resolved.append(controller_class)
        return controller

    endpoint = ControllerEndpointFactory(resolve).create(GreetingRestController, GreetingRestController.greet)

    assert endpoint(None, name="Ann")["message"] == "Hallo Ann"
    assert resolved == [GreetingRestController]


class OddController:
    async def asynchronous(self, request) -> None:  # type: ignore[no-untyped-def]
        """An async endpoint, which the library does not support."""

    @staticmethod
    def static(request) -> None:  # type: ignore[no-untyped-def]
        """A function without `self`."""


@pytest.mark.parametrize("method", [OddController.asynchronous, OddController.static], ids=["async", "static"])
def test_refuses_methods_it_cannot_serve(method) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(InvalidRestControllerError):
        ControllerEndpointFactory(lambda _: None).create(OddController, method)
