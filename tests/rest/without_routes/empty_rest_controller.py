from snakeboot.rest import rest_controller


@rest_controller("/empty")
class ControllerWithoutRoutes:
    """A controller someone forgot to give endpoints."""
