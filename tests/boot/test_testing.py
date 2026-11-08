"""A test starts the application with doubles and a database in memory, and calls its REST API in this process."""

from collections.abc import Iterator
from typing import override
from uuid import UUID

import pytest

from snakeboot.boot.testing import RestClient, RestResponse, TestApplication
from snakeboot.configuration import ServerProperties
from tests.application.sample_service.games.game_record import GameRecords
from tests.application.sample_service.games.game_rest_controller import Announcer
from tests.application.sample_service.sample_service_application import SampleServiceApplication


class RecordingAnnouncer(Announcer):
    def __init__(self) -> None:
        self.announced: list[UUID] = []

    @override
    def announce(self, game_id: UUID) -> None:
        self.announced.append(game_id)


@pytest.fixture
def announcer() -> RecordingAnnouncer:
    return RecordingAnnouncer()


@pytest.fixture
def application(announcer: RecordingAnnouncer) -> Iterator[TestApplication]:
    with TestApplication.start(SampleServiceApplication, overrides={Announcer: announcer}) as started:
        yield started


def test_the_api_saves_in_a_database_in_memory(application: TestApplication) -> None:
    client = application.client()

    created = client.post("/api/games", json={"status": "waiting"})
    found = client.get(f"/api/games/{created.json()['game_id']}")

    assert (created.status_code, found.json()["status"]) == (201, "waiting")
    assert application.get(GameRecords).count_by_status("waiting") == 1


def test_a_double_replaces_a_component_and_hears_after_the_commit(
    application: TestApplication, announcer: RecordingAnnouncer
) -> None:
    created = application.client().post("/api/games", json={"status": "waiting"}).json()

    assert announcer.announced == [UUID(created["game_id"])]


def test_an_advice_answers_through_the_client(application: TestApplication) -> None:
    client: RestClient = application.client()
    response: RestResponse = client.get("/api/games/00000000-0000-0000-0000-000000000000")

    assert (response.status_code, response.json()["code"]) == (404, "unknown_game")


def test_every_application_gets_a_fresh_database() -> None:
    for _ in range(2):
        with TestApplication.start(SampleServiceApplication) as started:
            assert started.get(GameRecords).count() == 0
            started.client().post("/api/games", json={"status": "waiting"})


def test_the_configuration_is_what_the_application_read(application: TestApplication) -> None:
    assert application.configuration.get(ServerProperties).allowed_hosts == ("*",)


def test_overrides_may_be_built_before_the_call(announcer: RecordingAnnouncer) -> None:
    overrides = {Announcer: announcer}

    with TestApplication.start(SampleServiceApplication, overrides=overrides) as started:
        assert started.get(Announcer) is announcer
