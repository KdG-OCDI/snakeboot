"""Auctions: closing one publishes an externalized event, and a projection reads it back from a stream."""

from dataclasses import dataclass
from typing import Annotated, Protocol

from pydantic import BaseModel

from snakeboot.component_scan import application_root
from snakeboot.data import Column, CrudRepository, Id, entity
from snakeboot.events import ApplicationEventPublisher, externalized
from snakeboot.rabbitmq import RejectAndDontRequeueError, rabbit_stream_listener
from snakeboot.stereotype import component
from snakeboot.transaction import transactional


@application_root
class AuctionsApplication:
    """A database and a broker: an auction house and, in the same application, a projection of its history."""


@externalized("auctions::auction.closed")
@dataclass(frozen=True)
class AuctionClosed:
    """The event of an auction that closed; its winning bid is negative for one that breaks the rules."""

    auction_id: str
    winning_bid: int


@component
class CloseAuction:
    """The use case: an auction closes, and its event goes to the broker too."""

    def __init__(self, events: ApplicationEventPublisher) -> None:
        self._events = events

    @transactional
    def execute(self, auction_id: str, winning_bid: int) -> None:
        """Closes the auction in a transaction."""
        self._events.publish(AuctionClosed(auction_id, winning_bid))

    @transactional
    def execute_and_fail(self, auction_id: str) -> None:
        """Closes the auction, then fails, so the transaction rolls back."""
        self._events.publish(AuctionClosed(auction_id, 1))
        raise RuntimeError("The transaction rolls back.")

    def execute_without_transaction(self, auction_id: str) -> None:
        """Closes the auction outside a transaction."""
        self._events.publish(AuctionClosed(auction_id, 1))


@entity("closed_auction")
@dataclass
class ClosedAuctionRecord:
    """The projection: what each closed auction fetched."""

    auction_id: Annotated[str, Id(), Column(length=100)]
    winning_bid: int


class ClosedAuctionRecords(CrudRepository[ClosedAuctionRecord, str], Protocol):
    """The closed auctions."""


class AuctionClosedMessage(BaseModel):
    """The event, as the stream holds it."""

    auction_id: str
    winning_bid: int


@component
class ClosedAuctionProjection:
    """Builds the projection from the stream of the auctions' history."""

    def __init__(self, records: ClosedAuctionRecords) -> None:
        self._records = records
        self.handled = 0

    @rabbit_stream_listener(stream="auctions.history", exchange="auctions", routing_key="auction.#")
    def on_auction_event(self, message: AuctionClosedMessage) -> None:
        """Keeps the winning bid of the auction; a negative one is refused for good, and the auction `crash` meets a
        database that fails after the record was saved."""
        self.handled += 1
        if message.winning_bid < 0:
            raise RejectAndDontRequeueError("A winning bid is never negative.")
        self._records.save(ClosedAuctionRecord(message.auction_id, message.winning_bid))
        if message.auction_id == "crash":
            raise RuntimeError("The database fails.")


@component
class PaymentProjection:
    """Reads the same stream with a routing key of its own: it hears no closed auction."""

    def __init__(self) -> None:
        self.heard: list[dict[str, object]] = []

    @rabbit_stream_listener(stream="auctions.history", exchange="auctions", routing_key="payment.#")
    def on_payment(self, message: dict[str, object]) -> None:
        """Keeps the payment."""
        self.heard.append(message)
