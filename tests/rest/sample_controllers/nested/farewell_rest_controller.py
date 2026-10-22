from snakeboot.rest import rest_controller, route


@rest_controller("/farewells")
class FarewellRestController:
    """Sample controller in a subpackage, without explicit tags."""

    @route.get("/{name}", response=dict[str, str])
    def say_goodbye(self, request, name: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
        return {"message": f"Tot ziens {name}"}
