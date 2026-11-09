from snakeboot.rest import rest_controller, roles_allowed, route


@rest_controller("/unchecked")
@roles_allowed("admin")
class UncheckedRestController:
    """Sample controller that names roles while the component scan declares no BearerAuthentication."""

    @route.get("")
    def everything(self) -> dict[str, str]:
        return {}
