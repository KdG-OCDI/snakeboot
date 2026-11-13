from snakeboot.rest import UploadedFile, rest_controller, route


@rest_controller("/imports")
class UploadByGetRestController:
    """Takes an upload on a GET, whose call carries no body."""

    @route.get("")
    def import_file(self, document: UploadedFile) -> int:
        return document.size
