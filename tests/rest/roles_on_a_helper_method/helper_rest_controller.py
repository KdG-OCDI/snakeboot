from snakeboot.rest import rest_controller, roles_allowed, route


@rest_controller("/helped")
class HelperRestController:
    """Sample controller with roles on a method that is no endpoint."""

    @route.get("")
    def everything(self) -> dict[str, str]:
        return self.helper()

    @roles_allowed("admin")
    def helper(self) -> dict[str, str]:
        return {}
