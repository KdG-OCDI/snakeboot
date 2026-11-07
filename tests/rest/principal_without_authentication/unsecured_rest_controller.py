from snakeboot.rest import Principal, rest_controller, route


@rest_controller("/unsecured")
class UnsecuredRestController:
    """Asks who called in an API that authenticates nobody."""

    @route.get("")
    def who_am_i(self, caller: Principal) -> str:
        return caller.name
