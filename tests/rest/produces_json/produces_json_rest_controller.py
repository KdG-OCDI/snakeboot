from snakeboot.rest import rest_controller, route


@rest_controller("/reports")
class ProducesJsonRestController:
    """Names the media type of a file on an endpoint that answers with JSON."""

    @route.get("", produces="text/csv")
    def report(self) -> dict[str, int]:
        return {"rows": 0}
