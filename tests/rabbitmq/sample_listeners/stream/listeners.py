"""A stream listener that builds a projection of bids, refuses some and fails on others."""

from pydantic import BaseModel

from snakeboot.rabbitmq import RejectAndDontRequeueError, rabbit_stream_listener
from snakeboot.tracing import TraceContext


class BidPlaced(BaseModel):
    """Stands in for the event another service externalized."""

    auction_id: str
    amount: int


class BidProjection:
    """Stands in for a projection: remembers every bid it read, and the trace it read it in."""

    def __init__(self) -> None:
        self.bids: list[BidPlaced] = []
        self.traces: list[str | None] = []
        self.attempts: dict[str, int] = {}

    @rabbit_stream_listener(stream="auctions.history", exchange="auctions", routing_key="auction.#")
    def on_bid(self, message: BidPlaced) -> None:
        """Keeps the bid. An auction `refuse` breaks the rules, `crash` always meets a database that is down,
        `flaky` only the first time."""
        attempt = self.attempts[message.auction_id] = self.attempts.get(message.auction_id, 0) + 1
        if message.auction_id == "flaky" and attempt == 1:
            raise RuntimeError("the database was down for a moment")
        if message.auction_id == "refuse":
            raise RejectAndDontRequeueError("this bid breaks the rules")
        if message.auction_id == "crash":
            raise RuntimeError("the database is down")
        span = TraceContext.current()
        self.traces.append(span.trace_id if span is not None else None)
        self.bids.append(message)
