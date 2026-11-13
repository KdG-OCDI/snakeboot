"""The shelves of the depot."""

from dataclasses import dataclass
from typing import Annotated, Protocol
from uuid import UUID

from snakeboot.data import Column, CrudRepository, Id, entity


@entity("depot_shelf")
@dataclass
class ShelfRecord:
    shelf_id: Annotated[UUID, Id()]
    label: Annotated[str, Column(length=40)]


class ShelfRecords(CrudRepository[ShelfRecord, UUID], Protocol):
    """The shelves."""
