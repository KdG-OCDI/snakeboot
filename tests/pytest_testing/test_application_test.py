"""`@application_test` starts the notebook anew for every test and hands each test what it asks for, by type.

These tests run through snakeboot's pytest plugin, as an application's tests do. The application is named: the source
of snakeboot's own tests holds many. `test_plugin_in_a_project.py` checks that a project with one finds it alone.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import override

import pytest

from snakeboot.boot.testing import RestClient
from snakeboot.cache import Cache, InMemoryCache
from snakeboot.testing import (
    Autowired,
    MockComponent,
    SpyComponent,
    application_test,
    signed_in_as,
    test_component,
    verify,
    when,
)
from snakeboot.testing.application_marker import APPLICATION_TEST_FIXTURE
from tests.pytest_testing.fixed_clock import START, FixedClock
from tests.pytest_testing.notebook.notebook_application import NotebookApplication
from tests.pytest_testing.notebook.notes import (
    Clock,
    LoggedNoticeBoard,
    NoteDTO,
    NotesProperties,
    NoteTooLongError,
    NoticeBoard,
    WriteNote,
)

notebook_test = application_test(application=NotebookApplication)

AS_A_WRITER = signed_in_as("ann", roles={"writer"})

MIDNIGHT = datetime(2026, 11, 12, tzinfo=UTC)


@notebook_test
def test_a_test_function_gets_its_parameters_by_type(
    client: Autowired[RestClient], clock: Autowired[FixedClock]
) -> None:
    clock.advance(timedelta(hours=1))

    response = client.post("/api/notes", json={"text": "hello"}, headers=AS_A_WRITER)

    assert response.status_code == 201
    assert response.json() == {"text": "hello", "writer": "ann", "written_at": "2026-11-12T10:00:00Z"}


@notebook_test
def test_the_other_parameters_stay_fixtures_of_pytest(client: Autowired[RestClient], tmp_path: Path) -> None:
    assert tmp_path.is_dir()
    assert client.get("/api/notes/last").status_code == 404


@notebook_test
def test_a_test_without_parameters_starts_the_application_too(request: pytest.FixtureRequest) -> None:
    assert APPLICATION_TEST_FIXTURE in request.fixturenames


@notebook_test
def test_a_test_component_replaces_the_component_and_is_found_by_its_own_type(
    clock: Autowired[Clock], fixed_clock: Autowired[FixedClock]
) -> None:
    assert clock is fixed_clock
    assert clock.now() == START


@notebook_test
def test_the_cache_of_a_test_lives_in_memory(cache: Autowired[Cache]) -> None:
    assert isinstance(cache, InMemoryCache)


@application_test(application=NotebookApplication, properties={"notes.max_length": 3})
def test_properties_win_over_the_files(client: Autowired[RestClient], properties: Autowired[NotesProperties]) -> None:
    assert properties.max_length == 3
    assert client.post("/api/notes", json={"text": "hello"}, headers=AS_A_WRITER).status_code == 422


@application_test(application=NotebookApplication, profile="short")
def test_a_profile_adds_its_file(properties: Autowired[NotesProperties]) -> None:
    assert properties.max_length == 5


@notebook_test
class TestAClassGetsItsFields:
    client: Autowired[RestClient]
    clock: Autowired[FixedClock]
    write_note: Autowired[WriteNote]

    def test_every_field_is_filled(self) -> None:
        note = self.write_note.execute("hi", "ann")

        assert note.written_at == START
        assert self.client.get("/api/notes/last").json()["text"] == "hi"

    def test_every_test_gets_an_application_of_its_own(self) -> None:
        assert self.clock.now() == START
        assert self.client.get("/api/notes/last").status_code == 404  # the note of the test above is gone

    def test_a_method_gets_its_parameters_too(self, board: Autowired[NoticeBoard]) -> None:
        assert isinstance(board, LoggedNoticeBoard)


@notebook_test
class TestAMockReplacesItsComponent:
    board: MockComponent[NoticeBoard]
    client: Autowired[RestClient]

    def test_the_application_uses_the_mock(self) -> None:
        self.client.post("/api/notes", json={"text": "hello"}, headers=AS_A_WRITER)

        verify(self.board.pin).called_once_with("hello")

    def test_when_says_what_the_mock_does(self) -> None:
        when(self.board.pin).then_raise(ConnectionError("The notice board is down."))

        with pytest.raises(ConnectionError):
            self.client.post("/api/notes", json={"text": "hello"}, headers=AS_A_WRITER)

    def test_every_test_gets_a_mock_of_its_own(self) -> None:
        verify(self.board.pin).never_called()


@notebook_test
class TestATestComponentNestedInTheClass:
    @test_component(replaces=NoticeBoard)
    class BoardThatIsDown:
        def pin(self, text: str) -> None:
            raise ConnectionError("The notice board is down.")

    @test_component(replaces=Clock)
    class StoppedClock(Clock):
        @override
        def now(self) -> datetime:
            return MIDNIGHT

    client: Autowired[RestClient]
    clock: Autowired[Clock]

    def test_it_replaces_its_component_for_the_tests_of_the_class(self) -> None:
        with pytest.raises(ConnectionError, match="The notice board is down"):
            self.client.post("/api/notes", json={"text": "hello"}, headers=AS_A_WRITER)

    def test_it_wins_over_the_test_component_of_the_project(self) -> None:
        assert self.clock.now() == MIDNIGHT

    def test_it_is_found_by_its_own_type(self, board: Autowired[BoardThatIsDown]) -> None:
        assert isinstance(board, TestATestComponentNestedInTheClass.BoardThatIsDown)

    @notebook_test
    class TestANestedClass:
        @test_component(replaces=NoticeBoard)
        class BoardThatRemembers:
            def __init__(self) -> None:
                self.pinned: list[str] = []

            def pin(self, text: str) -> None:
                self.pinned.append(text)

        client: Autowired[RestClient]
        clock: Autowired[Clock]
        board: Autowired[BoardThatRemembers]

        def test_it_sees_the_test_components_of_the_classes_around_it(self) -> None:
            assert self.clock.now() == MIDNIGHT

        def test_its_own_win_over_those_of_the_classes_around_it(self) -> None:
            response = self.client.post("/api/notes", json={"text": "hello"}, headers=AS_A_WRITER)

            assert (response.status_code, self.board.pinned) == (201, ["hello"])


@notebook_test
def test_a_test_component_nested_in_a_class_holds_nowhere_else(
    clock: Autowired[Clock], board: Autowired[NoticeBoard]
) -> None:
    assert isinstance(clock, FixedClock)
    assert isinstance(board, LoggedNoticeBoard)


@notebook_test
class TestASpyWrapsItsComponent:
    write_note: SpyComponent[WriteNote]
    client: Autowired[RestClient]

    def test_the_spy_does_what_the_component_does_and_records_the_call(self) -> None:
        response = self.client.post("/api/notes", json={"text": "hello"}, headers=AS_A_WRITER)

        assert NoteDTO.model_validate(response.json()).written_at == START
        verify(self.write_note.execute).called_once_with("hello", "ann")

    def test_when_changes_what_the_spy_does(self) -> None:
        when(self.write_note.execute).then_raise(NoteTooLongError("Too long, says the test."))

        response = self.client.post("/api/notes", json={"text": "hi"}, headers=AS_A_WRITER)

        assert (response.status_code, response.json()["detail"]) == (422, "Too long, says the test.")


@notebook_test
class TestSignedInAs:
    client: Autowired[RestClient]

    def test_a_caller_with_the_role_is_let_in(self) -> None:
        response = self.client.post("/api/notes", json={"text": "hello"}, headers=AS_A_WRITER)

        assert (response.status_code, response.json()["writer"]) == (201, "ann")

    def test_a_caller_without_the_role_is_forbidden(self) -> None:
        reader = signed_in_as("rob", roles={"reader"})

        assert self.client.post("/api/notes", json={"text": "hello"}, headers=reader).status_code == 403

    def test_a_call_without_a_token_is_unauthorized(self) -> None:
        assert self.client.post("/api/notes", json={"text": "hello"}).status_code == 401

    def test_the_tokens_of_the_application_still_count(self) -> None:
        response = self.client.post("/api/notes", json={"text": "hi"}, headers={"Authorization": "Bearer wendy-token"})

        assert (response.status_code, response.json()["writer"]) == (201, "wendy")

    @pytest.mark.parametrize("token", ["forged", "snakeboot-test.not-base64!", "snakeboot-test.e30="])
    def test_any_other_token_is_unauthorized(self, token: str) -> None:
        headers = {"Authorization": f"Bearer {token}"}

        assert self.client.post("/api/notes", json={"text": "hello"}, headers=headers).status_code == 401
