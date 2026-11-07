from typing import override

from snakeboot.rest import BearerAuthentication, Principal, rest_controller, route


class AnyToken(BearerAuthentication):
    @override
    def authenticate(self, token: str) -> str | None:
        return token


@rest_controller("/public")
class PublicRestController:
    """Asks who called on an endpoint that nobody has to sign in for."""

    @route.get("", public=True)
    def who_am_i(self, caller: Principal) -> str:
        return caller.name
