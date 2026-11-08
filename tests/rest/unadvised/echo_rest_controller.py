from pydantic import BaseModel

from snakeboot.rest import rest_controller, route


class EchoDTO(BaseModel):
    text: str


@rest_controller("/echo")
class EchoRestController:
    """A controller whose API has no advice for an invalid request."""

    @route.post("")
    def echo(self, body: EchoDTO) -> EchoDTO:
        return body
