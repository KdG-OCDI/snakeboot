"""An application whose migrations lack a column of its entity: a test on PostgreSQL stops on it."""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from snakeboot.component_scan import application_root
from snakeboot.data import Column, Id, entity


@application_root
class UnfitApplication:
    """Its migration creates the table `shelf` without the column `label`."""


@entity("shelf")
@dataclass
class ShelfRecord:
    shelf_id: Annotated[UUID, Id()]
    label: Annotated[str, Column(length=40)]
