from django.http import HttpRequest
from ninja import Schema, Status

from snakeboot.rest import error_answer, exception_handler, rest_controller, rest_controller_advice, route


class GreetingRequestBodyDTO(Schema):
    name: str


class UnknownNameError(Exception):
    """Stands in for an application error."""


class Greeter:
    """Stands in for a facade port."""

    def greet(self, name: str) -> str:
        if name == "nobody":
            raise UnknownNameError("Nobody is not a name.")
        return f"Hallo {name}"


@rest_controller("/greetings", tags=["greetings"])
class GreetingRestController:
    """Sample controller: one GET with a path parameter, one POST with a body."""

    def __init__(self, greeter: Greeter) -> None:
        self._greeter = greeter

    @route.get("/{name}", response=dict[str, str])
    def greet(self, request: HttpRequest, name: str) -> dict[str, str]:
        return {"message": self._greeter.greet(name), "controller": str(id(self))}

    @route.post("", response={201: dict[str, str]})
    def greet_from_body(self, request: HttpRequest, body: GreetingRequestBodyDTO) -> Status[dict[str, str]]:
        return Status(201, {"message": self._greeter.greet(body.name)})

    def helper_without_route(self) -> str:
        return "not an endpoint"


@rest_controller_advice
class GreetingRestErrorAdvice:
    """Sample advice: answers the error of the greeter for every controller."""

    @exception_handler(UnknownNameError, status=404)
    def answer_unknown_name(self, error: Exception) -> dict[str, str]:
        return error_answer(error)
