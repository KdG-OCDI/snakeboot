from snakeboot.rest import rest_controller, route
from tests.pytest_testing.library.catalogue.catalogue import Catalogue


@rest_controller("/books")
class CatalogueRestController:
    def __init__(self, catalogue: Catalogue) -> None:
        self._catalogue = catalogue

    @route.get("/{isbn}", public=True)
    def book(self, isbn: str) -> dict[str, object]:
        return {"isbn": isbn, "on_the_shelf": self._catalogue.is_on_the_shelf(isbn)}
