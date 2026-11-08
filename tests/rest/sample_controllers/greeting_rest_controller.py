from pydantic import BaseModel

from snakeboot.rest import (
    InvalidRequestError,
    error_answer,
    exception_handler,
    rest_controller,
    rest_controller_advice,
    route,
)


class GreetingRequestBodyDTO(BaseModel):
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
    """Sample controller: a GET with a path parameter, a POST with a body, a DELETE without an answer."""

    def __init__(self, greeter: Greeter) -> None:
        self._greeter = greeter

    @route.get("/{name}")
    def greet(self, name: str) -> dict[str, str]:
        return {"message": self._greeter.greet(name), "controller": str(id(self))}

    @route.post("", status=201)
    def greet_from_body(self, body: GreetingRequestBodyDTO) -> dict[str, str]:
        return {"message": self._greeter.greet(body.name)}

    @route.delete("/{name}", status=204)
    def forget(self, name: str) -> None:
        self._greeter.greet(name)

    def helper_without_route(self) -> str:
        return "not an endpoint"


@rest_controller_advice
class GreetingRestErrorAdvice:
    """Sample advice: answers the error of the greeter for every controller."""

    @exception_handler(UnknownNameError, status=404)
    def answer_unknown_name(self, error: Exception) -> dict[str, str]:
        return error_answer(error)

    @exception_handler(InvalidRequestError, status=422)
    def answer_invalid_request(self, error: Exception) -> dict[str, str]:
        return error_answer(error)
