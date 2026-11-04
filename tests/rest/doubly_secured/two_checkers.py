from typing import override

from snakeboot.rest import BearerAuthentication


class FirstChecker(BearerAuthentication):
    @override
    def authenticate(self, token: str) -> str | None:
        return None


class SecondChecker(BearerAuthentication):
    @override
    def authenticate(self, token: str) -> str | None:
        return None
