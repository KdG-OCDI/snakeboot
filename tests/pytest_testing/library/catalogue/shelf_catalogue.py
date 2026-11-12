from typing import Final, override

from wireup import injectable

from tests.pytest_testing.library.catalogue.catalogue import Catalogue

ON_THE_SHELF: Final = frozenset({"978-0-00-000001-1"})


@injectable(as_type=Catalogue)
class ShelfCatalogue(Catalogue):
    """The catalogue of the shelf itself."""

    @override
    def is_on_the_shelf(self, isbn: str) -> bool:
        return isbn in ON_THE_SHELF
