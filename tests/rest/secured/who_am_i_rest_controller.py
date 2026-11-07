from snakeboot.rest import Principal, rest_controller, route


@rest_controller("/me")
class WhoAmIRestController:
    """Sample controller of a secured API: one endpoint asks who called, one answers anybody."""

    @route.get("")
    def who_am_i(self, caller: Principal) -> dict[str, str]:
        return {"name": caller.name}

    @route.get("/door", public=True)
    def open_door(self) -> dict[str, str]:
        return {"door": "open"}
