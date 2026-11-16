from snakeboot.rest import roles_allowed
from snakeboot.stereotype import service


@service
class SecuredService:
    """Sample service that names roles, which no HTTP binding checks on a direct call."""

    @roles_allowed("admin")
    def execute(self) -> str:
        return "executed"
