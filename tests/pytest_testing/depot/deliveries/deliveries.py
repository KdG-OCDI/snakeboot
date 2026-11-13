"""The deliveries of the depot: a context whose own migrations hold none of snakeboot's tables."""

from dataclasses import dataclass
from typing import Annotated, Protocol
from uuid import UUID

from snakeboot.data import Column, CrudRepository, Id, entity


@entity("depot_delivery")
@dataclass
class DeliveryRecord:
    delivery_id: Annotated[UUID, Id()]
    sender: Annotated[str, Column(length=100)]


class DeliveryRecords(CrudRepository[DeliveryRecord, UUID], Protocol):
    """The deliveries."""
