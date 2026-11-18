"""An application with an externalized event, but without a broker to send it."""

from dataclasses import dataclass

from snakeboot.component_scan import application_root
from snakeboot.events import externalized


@application_root
class AuctionsWithoutBrokerApplication:
    """A database, and no [rabbitmq]."""


@externalized("auctions::auction.closed")
@dataclass(frozen=True)
class AuctionClosed:
    """An event no broker would send."""

    auction_id: str
