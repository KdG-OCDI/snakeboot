"""Tests that ask the same application share one start of it, reset in between, like Spring's test context cache.

The tests of a class run in the order they are written: the first leaves its traces, the next ones look for them.
"""

from datetime import timedelta

import pytest

from snakeboot.boot.testing import TestApplication
from snakeboot.cache import Cache
from snakeboot.pytest_testing import kept_applications
from snakeboot.pytest_testing.kept_applications import ApplicationSetUp, KeptApplications
from snakeboot.rabbitmq import InProcessRabbitTemplate
from snakeboot.testing import (
    Autowired,
    MockComponent,
    PostgreSQLContainer,
    PublishedEvents,
    SpyComponent,
    TestEnvironment,
    application_test,
    dirties_application,
    verify,
    when,
)
from snakeboot.transaction import TransactionManagerRegistry
from tests.containers import docker_runs
from tests.pytest_testing.fixed_clock import START, FixedClock
from tests.pytest_testing.notebook.notebook_application import NotebookApplication
from tests.pytest_testing.notebook.notes import LAST_NOTE, NoticeBoard, WriteNote
from tests.pytest_testing.parcels.parcels import ParcelRecords, ParcelsApplication, SendParcel

notebook_test = application_test(application=NotebookApplication)
parcels_test = application_test(application=ParcelsApplication)

SEEN: dict[str, object] = {}
"""What an earlier test was handed, for the next one to compare with."""


@notebook_test
class TestTheNextTestGetsTheSameApplication:
    write_note: Autowired[WriteNote]
    clock: Autowired[FixedClock]
    cache: Autowired[Cache]

    def test_a_test_leaves_its_traces(self) -> None:
        SEEN.update(write_note=self.write_note, clock=self.clock)
        self.clock.advance(timedelta(hours=1))

        self.write_note.execute("hello", "ann")

        assert self.cache.get(LAST_NOTE) is not None

    def test_the_application_is_the_one_that_was_started(self) -> None:
        assert self.write_note is SEEN["write_note"]

    def test_its_cache_is_empty(self) -> None:
        assert self.cache.get(LAST_NOTE) is None

    def test_its_test_components_are_built_anew_in_place(self) -> None:
        assert self.clock is SEEN["clock"]
        assert self.clock.now() == START


@notebook_test
class TestAMockForgets:
    board: MockComponent[NoticeBoard]
    write_note: Autowired[WriteNote]

    def test_a_test_tells_a_mock_what_to_answer(self) -> None:
        SEEN.update(board=self.board)
        when(self.board.pin).then_raise(ConnectionError("down"))

        with pytest.raises(ConnectionError):
            self.write_note.execute("hello", "ann")

    def test_the_next_test_gets_the_mock_without_its_answers_and_its_calls(self) -> None:
        assert self.board is SEEN["board"]
        verify(self.board.pin).never_called()

        self.write_note.execute("hello", "ann")

        verify(self.board.pin).called_once_with("hello")


@notebook_test
class TestASpyForgets:
    board: SpyComponent[NoticeBoard]
    write_note: Autowired[WriteNote]

    def test_a_test_tells_a_spy_what_to_answer(self) -> None:
        when(self.board.pin).then_raise(ConnectionError("down"))

        with pytest.raises(ConnectionError):
            self.write_note.execute("hello", "ann")

    def test_the_next_test_gets_the_spy_around_the_component_again(self) -> None:
        verify(self.board.pin).never_called()

        self.write_note.execute("hello", "ann")

        verify(self.board.pin).called_once_with("hello")


@parcels_test
class TestTheDatabaseTheEventsAndTheBrokerStartEmpty:
    send_parcel: Autowired[SendParcel]
    parcels: Autowired[ParcelRecords]
    events: Autowired[PublishedEvents]
    rabbit: Autowired[InProcessRabbitTemplate]

    def test_a_test_sends_a_parcel(self) -> None:
        SEEN.update(send_parcel=self.send_parcel)

        self.send_parcel.execute("ann")

        assert (self.parcels.count(), len(self.events), len(self.rabbit.sent)) == (1, 1, 1)

    def test_the_next_test_finds_none_of_it(self) -> None:
        assert self.send_parcel is SEEN["send_parcel"]
        assert (self.parcels.count(), len(self.events), len(self.rabbit.sent)) == (0, 0, 0)


def test_between_two_tests_transactional_is_no_application_s() -> None:
    assert not TransactionManagerRegistry.is_installed()


@parcels_test
def test_a_kept_application_runs_its_transactions_again(
    send_parcel: Autowired[SendParcel], parcels: Autowired[ParcelRecords]
) -> None:
    assert send_parcel is SEEN["send_parcel"]

    send_parcel.execute("bob")

    assert parcels.count() == 1


@application_test(application=NotebookApplication, properties={"notes.max_length": 5})
def test_other_properties_start_another_application(write_note: Autowired[WriteNote]) -> None:
    assert write_note is not SEEN["write_note"]


@notebook_test
@dirties_application
def test_a_test_that_dirties_the_application_gets_the_kept_one(write_note: Autowired[WriteNote]) -> None:
    assert write_note is SEEN["write_note"]


@notebook_test
def test_and_the_test_after_it_starts_the_application_anew(write_note: Autowired[WriteNote]) -> None:
    assert write_note is not SEEN["write_note"]


@notebook_test
@dirties_application
class TestEveryTestOfADirtyingClassStartsAnew:
    write_note: Autowired[WriteNote]

    def test_a_test_gets_an_application(self) -> None:
        SEEN.update(dirtied=self.write_note)

    def test_the_next_one_gets_another(self) -> None:
        assert self.write_note is not SEEN["dirtied"]


def _notebook_with(max_length: int) -> ApplicationSetUp:
    environment = TestEnvironment(properties={"notes.max_length": max_length})
    return ApplicationSetUp(NotebookApplication, environment, None, mocked=(), spied=(), test_components={})


def test_beyond_the_limit_the_application_that_ran_longest_ago_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kept_applications, "KEPT_AT_MOST", 1)
    kept = KeptApplications()
    longest_ago = kept.running(_notebook_with(5))
    kept.keep(_notebook_with(5), longest_ago)
    latest = kept.running(_notebook_with(6))

    kept.keep(_notebook_with(6), latest)

    with pytest.raises(LookupError, match="not started"):
        longest_ago.application.get(WriteNote)
    assert latest.application.get(WriteNote) is not None
    kept.close()


def test_the_end_of_the_run_closes_every_kept_application() -> None:
    kept = KeptApplications()
    running = kept.running(_notebook_with(7))
    kept.keep(_notebook_with(7), running)

    kept.close()

    with pytest.raises(LookupError, match="not started"):
        running.application.get(WriteNote)


def test_reset_puts_back_the_database_the_migrations_built() -> None:
    with TestApplication.start(ParcelsApplication) as app:
        app.get(SendParcel).execute("ann")

        app.reset()
        app.resume()

        assert app.get(ParcelRecords).count() == 0
        app.get(SendParcel).execute("bob")
        assert app.get(ParcelRecords).count() == 1


@pytest.mark.skipif(not docker_runs(), reason="a PostgreSQLContainer needs a running Docker")
def test_reset_copies_the_template_of_postgresql_anew() -> None:
    environment = TestEnvironment(database=PostgreSQLContainer())
    with TestApplication.start(ParcelsApplication, environment=environment) as app:
        app.get(SendParcel).execute("ann")

        app.reset()
        app.resume()

        assert app.get(ParcelRecords).count() == 0
        app.get(SendParcel).execute("bob")
        assert app.get(ParcelRecords).count() == 1
