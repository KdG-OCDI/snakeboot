"""`@externalized` names where the events of a class go; the start refuses them when no broker sends them."""

from dataclasses import dataclass

import pytest
from pydantic import BaseModel

from snakeboot.events import (
    EventExternalization,
    ExternalizationTarget,
    InvalidExternalizationError,
    externalization_target,
    externalized,
)
from snakeboot.events.externalized import EXTERNALIZED_ATTRIBUTE, refuse_externalized_events_nobody_sends


@externalized("auctions::auction.closed")
@dataclass(frozen=True, slots=True)
class AuctionClosed:
    auction_id: str


@dataclass(frozen=True, slots=True)
@externalized("auctions::auction.opened")
class AuctionOpened:
    """Marked beneath a dataclass with slots, which makes a class of its own: the mark goes with it."""

    auction_id: str


class AuctionClosedLate(AuctionClosed):
    """A subclass goes where its base class goes."""


@externalized("auctions::bid.placed")
class BidPlaced(BaseModel):
    auction_id: str


@dataclass(frozen=True)
class BidWithdrawn:
    auction_id: str


def test_the_target_names_the_exchange_and_the_routing_key() -> None:
    assert externalization_target(AuctionClosed("a1")) == ExternalizationTarget("auctions", "auction.closed")
    assert externalization_target(BidPlaced(auction_id="a1")) == ExternalizationTarget("auctions", "bid.placed")


def test_the_mark_survives_a_dataclass_with_slots_above_it() -> None:
    assert EXTERNALIZED_ATTRIBUTE in vars(AuctionOpened)
    assert externalization_target(AuctionOpened("a1")).key == "auction.opened"


def test_a_subclass_goes_where_its_base_class_goes() -> None:
    assert externalization_target(AuctionClosedLate("a1")).key == "auction.closed"


def test_an_event_that_is_not_externalized_has_no_target() -> None:
    with pytest.raises(InvalidExternalizationError, match="is not @externalized"):
        externalization_target(BidWithdrawn("a1"))


@pytest.mark.parametrize("target", ["auctions", "auctions::", "::auction.closed", ""])
def test_a_target_without_an_exchange_and_a_key_is_refused(target: str) -> None:
    with pytest.raises(InvalidExternalizationError, match="names a target and a key"):
        externalized(target)


def test_externalized_events_that_no_broker_sends_stop_the_start() -> None:
    with pytest.raises(InvalidExternalizationError, match=r"AuctionClosed, BidPlaced @externalized.*\[rabbitmq\]"):
        refuse_externalized_events_nobody_sends([BidPlaced, AuctionClosed], [object()])


def test_a_broker_that_sends_them_lets_the_application_start() -> None:
    refuse_externalized_events_nobody_sends([AuctionClosed], [EventExternalization()])


def test_an_application_without_externalized_events_needs_no_broker() -> None:
    refuse_externalized_events_nobody_sends([], [])
