"""`@externalized` names where the events of a class go, and makes them `ExternalizedEvent`s for one listener."""

from dataclasses import dataclass
from typing import cast

import pytest
from pydantic import BaseModel

from snakeboot.event_publication import PersistentEventPublicationRegistry
from snakeboot.event_publication.event_publication_record import EventPublicationRecords
from snakeboot.events import (
    ExternalizationTarget,
    ExternalizedEvent,
    InvalidExternalizationError,
    externalization_target,
    externalized,
)
from snakeboot.rabbitmq import EventExternalizer


@externalized("auctions::auction.closed")
@dataclass(frozen=True, slots=True)
class AuctionClosed:
    auction_id: str


class AuctionClosedLate(AuctionClosed):
    """A subclass goes where its base class goes."""


@externalized("auctions::bid.placed")
class BidPlaced(BaseModel):
    auction_id: str


@dataclass(frozen=True)
class AuctionOpened:
    auction_id: str


class NotJson:
    """An event the registry cannot keep as JSON."""


def test_the_events_of_an_externalized_class_are_externalized_events() -> None:
    assert isinstance(AuctionClosed("a1"), ExternalizedEvent)
    assert isinstance(BidPlaced(auction_id="a1"), ExternalizedEvent)
    assert not isinstance(AuctionOpened("a1"), ExternalizedEvent)


def test_the_target_names_the_exchange_and_the_routing_key() -> None:
    assert externalization_target(AuctionClosed("a1")) == ExternalizationTarget("auctions", "auction.closed")
    assert externalization_target(BidPlaced(auction_id="a1")) == ExternalizationTarget("auctions", "bid.placed")


def test_a_subclass_goes_where_its_base_class_goes() -> None:
    assert isinstance(AuctionClosedLate("a1"), ExternalizedEvent)
    assert externalization_target(AuctionClosedLate("a1")).key == "auction.closed"


def test_an_event_that_is_not_externalized_has_no_target() -> None:
    with pytest.raises(InvalidExternalizationError, match="is not @externalized"):
        externalization_target(AuctionOpened("a1"))


@pytest.mark.parametrize("target", ["auctions", "auctions::", "::auction.closed", ""])
def test_a_target_without_an_exchange_and_a_key_is_refused(target: str) -> None:
    with pytest.raises(InvalidExternalizationError, match="names a target and a key"):
        externalized(target)


def test_an_event_the_registry_cannot_keep_stops_the_start() -> None:
    registry = PersistentEventPublicationRegistry(cast(EventPublicationRecords, None))  # verify reads no record

    EventExternalizer.verify([AuctionClosed, BidPlaced], [registry])
    with pytest.raises(InvalidExternalizationError, match="kept as JSON"):
        EventExternalizer.verify([NotJson], [registry])


def test_without_a_registry_nothing_needs_to_be_kept() -> None:
    EventExternalizer.verify([NotJson], [])
