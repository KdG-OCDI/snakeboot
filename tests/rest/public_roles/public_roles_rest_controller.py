from snakeboot.rest import rest_controller, roles_allowed, route


@rest_controller("/open")
class PublicRolesRestController:
    """Sample controller that names roles on a public endpoint, which nobody can check."""

    @route.get("", public=True)
    @roles_allowed("admin")
    def everybody(self) -> dict[str, str]:
        return {}
