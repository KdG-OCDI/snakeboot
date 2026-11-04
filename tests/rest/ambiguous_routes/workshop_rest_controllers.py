from snakeboot.rest import rest_controller, route


@rest_controller("/workshops")
class WorkshopsByWorkshopId:
    @route.get("/{workshop_id}")
    def get_workshop(self, request: object, workshop_id: str) -> None: ...


@rest_controller("/workshops/")
class WorkshopsById:
    @route.get("{id}")
    def find_workshop(self, request: object, id: str) -> None: ...  # noqa: A002  # reason: the path parameter under test
