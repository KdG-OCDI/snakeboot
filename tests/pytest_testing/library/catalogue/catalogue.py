from abc import ABC, abstractmethod


class Catalogue(ABC):
    """The public face of the catalogue: whether a book is on the shelf. Loans asks it."""

    @abstractmethod
    def is_on_the_shelf(self, isbn: str) -> bool:
        """Tells whether the book `isbn` is on the shelf."""
