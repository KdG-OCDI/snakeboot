"""Parcels: sent with an event and a message to the carrier, delivered when the carrier's message comes back."""

from dataclasses import dataclass
from typing import Annotated, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel

from snakeboot.component_scan import application_root
from snakeboot.data import Column, CrudRepository, Id, entity
from snakeboot.events import ApplicationEventPublisher
from snakeboot.rabbitmq import RabbitTemplate, RejectAndDontRequeueError, rabbit_listener
from snakeboot.stereotype import component
from snakeboot.transaction import transactional

EXCHANGE = "parcels"


@application_root
class ParcelsApplication:
    """A database, events and a broker: what `PostgreSQLContainer`, `PublishedEvents` and the template replace."""


@entity("parcel")
@dataclass
class ParcelRecord:
    parcel_id: Annotated[UUID, Id()]
    recipient: Annotated[str, Column(length=100)]
    status: Annotated[str, Column(length=16)]


class ParcelRecords(CrudRepository[ParcelRecord, UUID], Protocol):
    """The parcels."""


@dataclass(frozen=True)
class ParcelSent:
    """The event of a parcel that left."""

    parcel_id: UUID
    recipient: str


class ParcelSentMessage(BaseModel):
    parcel_id: UUID
    recipient: str


class ParcelDeliveredMessage(BaseModel):
    parcel_id: UUID


@component
class SendParcel:
    """The use case: a parcel is kept, its event published and the carrier asked to deliver it."""

    def __init__(self, parcels: ParcelRecords, events: ApplicationEventPublisher, rabbit: RabbitTemplate) -> None:
        self._parcels = parcels
        self._events = events
        self._rabbit = rabbit

    @transactional
    def execute(self, recipient: str) -> UUID:
        """Sends a parcel to `recipient` and returns its id."""
        parcel = self._parcels.save(ParcelRecord(uuid4(), recipient, "SENT"))
        self._events.publish(ParcelSent(parcel.parcel_id, recipient))
        message = ParcelSentMessage(parcel_id=parcel.parcel_id, recipient=recipient)
        self._rabbit.convert_and_send(EXCHANGE, f"parcel.{parcel.parcel_id}.sent", message)
        return parcel.parcel_id


@component
class ParcelDeliveredListener:
    """Hears from the carrier that a parcel arrived; an unknown parcel is refused for good, into the dead-letter
    queue."""

    def __init__(self, parcels: ParcelRecords) -> None:
        self._parcels = parcels

    @rabbit_listener(queue="parcels.delivered", exchange=EXCHANGE, routing_key="parcel.*.delivered", dead_letter=True)
    @transactional
    def on_parcel_delivered(self, message: ParcelDeliveredMessage) -> None:
        """Marks the parcel delivered."""
        parcel = self._parcels.find_by_id(message.parcel_id)
        if parcel is None:
            raise RejectAndDontRequeueError(f"No parcel has the id {message.parcel_id}.")
        parcel.status = "DELIVERED"
        self._parcels.save(parcel)


@component
class CarrierListener:
    """Stands in for the carrier on the same broker: it hears every message about a parcel."""

    def __init__(self) -> None:
        self.heard: list[str] = []

    @rabbit_listener(queue="carrier.parcels", exchange=EXCHANGE, routing_key="parcel.#")
    def on_parcel(self, message: dict[str, object]) -> None:
        """Keeps the recipient of the message."""
        self.heard.append(str(message.get("recipient")))
