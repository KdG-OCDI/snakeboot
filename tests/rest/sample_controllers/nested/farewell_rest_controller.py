from snakeboot.rest import rest_controller, route


@rest_controller("/farewells")
class FarewellRestController:
    """Sample controller in a subpackage, without explicit tags."""

    @route.get("/{name}")
    def say_goodbye(self, name: str) -> dict[str, str]:
        return {"message": f"Tot ziens {name}"}
