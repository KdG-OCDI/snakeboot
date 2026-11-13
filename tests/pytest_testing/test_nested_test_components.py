"""In a project of its own, a `@test_component` nested in a test class replaces its component for that class only.

Like a static nested `@TestConfiguration` in Spring Boot: the auction house's repository loses the update of a bid
for one test class, which shows the 409 of the lost update, while every other test keeps the application's own.
"""

from pathlib import Path

import pytest

from tests.pytest_testing.test_plugin_in_a_project import SERVER

AUCTION_HOUSE_APPLICATION = """\
from snakeboot.component_scan import application_root


@application_root
class AuctionHouseApplication:
    '''An auction house that takes bids.'''
"""

AUCTIONS = """\
from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic import BaseModel
from wireup import injectable

from snakeboot.rest import error_answer, exception_handler, rest_controller, rest_controller_advice, route


@dataclass
class Auction:
    auction_id: str
    highest_bid: int


class AuctionChangedMeanwhileError(RuntimeError):
    pass


class AuctionRepositoryPort(ABC):
    @abstractmethod
    def get(self, auction_id: str) -> Auction: ...

    @abstractmethod
    def save(self, auction: Auction) -> None: ...


@injectable(as_type=AuctionRepositoryPort)
class InMemoryAuctionRepository(AuctionRepositoryPort):
    def __init__(self) -> None:
        self._auctions = {"a1": Auction("a1", highest_bid=100)}

    def get(self, auction_id: str) -> Auction:
        return self._auctions[auction_id]

    def save(self, auction: Auction) -> None:
        self._auctions[auction.auction_id] = auction


class BidDTO(BaseModel):
    amount: int


@rest_controller("/auctions")
class AuctionRestController:
    def __init__(self, auctions: AuctionRepositoryPort) -> None:
        self._auctions = auctions

    @route.post("/{auction_id}/bids", status=201)
    def bid(self, auction_id: str, body: BidDTO) -> dict[str, int]:
        auction = self._auctions.get(auction_id)
        auction.highest_bid = body.amount
        self._auctions.save(auction)
        return {"highest_bid": auction.highest_bid}


@rest_controller_advice
class AuctionErrorAdvice:
    @exception_handler(AuctionChangedMeanwhileError, status=409)
    def answer_changed_meanwhile(self, error: Exception) -> dict[str, str]:
        return error_answer(error)
"""

TESTS = """\
from auction_house.auctions import Auction, AuctionChangedMeanwhileError, AuctionRepositoryPort
from snakeboot.boot.testing import RestClient
from snakeboot.testing import Autowired, application_test, test_component


@application_test
class TestWithARepositoryThatLosesTheUpdate:
    @test_component(replaces=AuctionRepositoryPort)
    class RepositoryThatLosesTheUpdate:
        def get(self, auction_id: str) -> Auction:
            return Auction(auction_id, highest_bid=100)

        def save(self, auction: Auction) -> None:
            raise AuctionChangedMeanwhileError("Another bid came in meanwhile.")

    client: Autowired[RestClient]

    def test_a_lost_update_answers_409(self) -> None:
        response = self.client.post("/api/auctions/a1/bids", json={"amount": 120})

        assert (response.status_code, response.json()["detail"]) == (409, "Another bid came in meanwhile.")

    @application_test
    class TestANestedClass:
        auctions: Autowired[AuctionRepositoryPort]

        def test_it_has_the_test_component_of_the_class_around_it(self) -> None:
            assert type(self.auctions).__name__ == "RepositoryThatLosesTheUpdate"

        @application_test
        class TestWithARepositoryOfItsOwn:
            @test_component(replaces=AuctionRepositoryPort)
            class RepositoryWithoutAuctions:
                def get(self, auction_id: str) -> Auction:
                    raise KeyError(auction_id)

                def save(self, auction: Auction) -> None:
                    pass

            auctions: Autowired[AuctionRepositoryPort]

            def test_its_own_wins(self) -> None:
                assert type(self.auctions).__name__ == "RepositoryWithoutAuctions"


@application_test
def test_every_other_test_keeps_the_repository_of_the_application(client: Autowired[RestClient]) -> None:
    response = client.post("/api/auctions/a1/bids", json={"amount": 120})

    assert (response.status_code, response.json()) == (201, {"highest_bid": 120})
"""

OTHER_TESTS = """\
from auction_house.auctions import AuctionRepositoryPort, InMemoryAuctionRepository
from snakeboot.testing import Autowired, application_test


@application_test
def test_a_test_of_another_module_keeps_the_repository_of_the_application(
    auctions: Autowired[AuctionRepositoryPort],
) -> None:
    assert isinstance(auctions, InMemoryAuctionRepository)
"""

INVALID_TESTS = """\
from auction_house.auctions import Auction, AuctionRepositoryPort
from snakeboot.testing import MockComponent, application_test, test_component


@application_test
class TestAMockBesideATestComponent:
    @test_component(replaces=AuctionRepositoryPort)
    class RepositoryThatLosesTheUpdate:
        def get(self, auction_id: str) -> Auction: ...

        def save(self, auction: Auction) -> None: ...

    auctions: MockComponent[AuctionRepositoryPort]

    def test_never_runs(self) -> None:
        raise AssertionError("The test itself never runs.")


@application_test
class TestATestComponentThatNeedsArguments:
    @test_component(replaces=AuctionRepositoryPort)
    class RepositoryOfSomeAuctions:
        def __init__(self, auctions: list[Auction]) -> None:
            self._auctions = auctions

    def test_never_runs(self) -> None:
        raise AssertionError("The test itself never runs.")
"""


def write_auction_house(directory: Path) -> None:
    auction_house = directory / "auction_house"
    auction_house.mkdir()
    (auction_house / "__init__.py").write_text("")
    (auction_house / "application.toml").write_text(SERVER)
    (auction_house / "auction_house_application.py").write_text(AUCTION_HOUSE_APPLICATION)
    (auction_house / "auctions.py").write_text(AUCTIONS)
    (directory / "test_optimistic_locking.py").write_text(TESTS)
    (directory / "test_bids.py").write_text(OTHER_TESTS)


def test_a_nested_test_component_replaces_its_component_for_its_class_only(pytester: pytest.Pytester) -> None:
    write_auction_house(pytester.path)

    result = pytester.runpytest_subprocess("-p", "no:cacheprovider")

    result.assert_outcomes(passed=5)


def test_a_nested_test_component_that_does_not_fit_stops_the_test(pytester: pytest.Pytester) -> None:
    write_auction_house(pytester.path)
    (pytester.path / "test_invalid.py").write_text(INVALID_TESTS)

    result = pytester.runpytest_subprocess("-p", "no:cacheprovider", "test_invalid.py")

    result.assert_outcomes(errors=2)
    result.stdout.fnmatch_lines_random(
        [
            "*RepositoryThatLosesTheUpdate and a MockComponent both replace AuctionRepositoryPort in one test class*",
            "*A test component is built without arguments; *RepositoryOfSomeAuctions*",
        ]
    )
