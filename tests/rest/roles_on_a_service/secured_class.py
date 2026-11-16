from snakeboot.rest import roles_allowed
from snakeboot.stereotype import service


@service
@roles_allowed("admin")
class SecuredClass:
    """Sample service whose class names roles."""

    def execute(self) -> str:
        return "executed"
