from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Protocol

from snakeboot.data import CrudRepository, Id, entity
from snakeboot.events import ApplicationEventPublisher, application_event_listener, application_module_listener
from snakeboot.stereotype import service
from snakeboot.transaction import transactional


@dataclass(frozen=True)
class OrderPlaced:
    order_id: str
    amount: int
    placed_at: datetime


@entity("outbox_order")
@dataclass
class OrderRecord:
    order_id: Annotated[str, Id()]
    amount: int


class OrderRecords(CrudRepository[OrderRecord, str], Protocol):
    """The orders placed."""


@entity("outbox_invoice")
@dataclass
class InvoiceRecord:
    order_id: Annotated[str, Id()]
    amount: int


class InvoiceRecords(CrudRepository[InvoiceRecord, str], Protocol):
    """The invoices sent."""


@service
class InvoicingService:
    """Stands in for a service the invoicing module calls; a test takes it down."""

    def __init__(self) -> None:
        self.down = False


@service
class PlaceOrderUseCase:
    def __init__(self, orders: OrderRecords, events: ApplicationEventPublisher) -> None:
        self._orders = orders
        self._events = events

    @transactional
    def execute(self, order_id: str, amount: int, placed_at: datetime) -> None:
        self._orders.save(OrderRecord(order_id, amount))
        self._events.publish(OrderPlaced(order_id, amount, placed_at))


@application_event_listener
class InvoiceOnOrderPlaced:
    def __init__(self, invoices: InvoiceRecords, service: InvoicingService) -> None:
        self._invoices = invoices
        self._service = service

    @application_module_listener(OrderPlaced)
    def invoice(self, event: OrderPlaced) -> None:
        self._invoices.save(InvoiceRecord(event.order_id, event.amount))
        if self._service.down:
            raise ConnectionError("the invoicing service is down")
