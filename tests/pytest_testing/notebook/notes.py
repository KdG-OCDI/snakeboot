from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import override

from pydantic import BaseModel

from snakeboot.cache import Cache
from snakeboot.configuration import Section, configuration_properties
from snakeboot.rest import (
    BearerAuthentication,
    error_answer,
    exception_handler,
    rest_controller,
    rest_controller_advice,
    roles_allowed,
    route,
)
from snakeboot.security import Principal
from snakeboot.stereotype import component

LAST_NOTE = "last-note"


@configuration_properties("notes")
class NotesProperties(Section):
    """The section `[notes]`: how long a note may be."""

    max_length: int


class Clock(ABC):
    """A port: what time it is."""

    @abstractmethod
    def now(self) -> datetime:
        """Returns the moment it is now."""


@component(as_type=Clock)
class SystemClock(Clock):
    """The time of the machine."""

    @override
    def now(self) -> datetime:
        return datetime.now(UTC)


class NoticeBoard(ABC):
    """A port: where a note is pinned for everyone to see."""

    @abstractmethod
    def pin(self, text: str) -> None:
        """Pins `text` to the board."""


@component(as_type=NoticeBoard)
class LoggedNoticeBoard(NoticeBoard):
    """A board that only remembers what was pinned."""

    def __init__(self) -> None:
        self.pinned: list[str] = []

    @override
    def pin(self, text: str) -> None:
        self.pinned.append(text)


class NoteTooLongError(ValueError):
    """The note is longer than `[notes] max_length`."""


class NoNoteYetError(LookupError):
    """Nobody wrote a note yet."""


class NewNoteDTO(BaseModel):
    text: str


class NoteDTO(BaseModel):
    text: str
    writer: str
    written_at: datetime


@component
class WriteNote:
    """The use case: a writer writes a note, which is pinned and kept as the last one."""

    def __init__(self, properties: NotesProperties, clock: Clock, board: NoticeBoard, cache: Cache) -> None:
        self._max_length = properties.max_length
        self._clock = clock
        self._board = board
        self._cache = cache

    def execute(self, text: str, writer: str) -> NoteDTO:
        """Writes the note `text` of `writer`."""
        if len(text) > self._max_length:
            raise NoteTooLongError(f"A note has at most {self._max_length} characters.")
        note = NoteDTO(text=text, writer=writer, written_at=self._clock.now())
        self._board.pin(text)
        self._cache.put(LAST_NOTE, note.model_dump(mode="json"))
        return note


@rest_controller("/notes")
class NoteRestController:
    def __init__(self, write_note: WriteNote, cache: Cache) -> None:
        self._write_note = write_note
        self._cache = cache

    @route.post("", status=201)
    @roles_allowed("writer")
    def write(self, body: NewNoteDTO, writer: Principal) -> NoteDTO:
        return self._write_note.execute(body.text, writer.name)

    @route.get("/last", public=True)
    def last(self) -> NoteDTO:
        note = self._cache.get(LAST_NOTE)
        if note is None:
            raise NoNoteYetError("Nobody wrote a note yet.")
        return NoteDTO.model_validate(note)


@rest_controller_advice
class NoteErrorAdvice:
    @exception_handler(NoteTooLongError, status=422)
    def answer_too_long(self, error: Exception) -> dict[str, str]:
        return error_answer(error)

    @exception_handler(NoNoteYetError, status=404)
    def answer_no_note_yet(self, error: Exception) -> dict[str, str]:
        return error_answer(error)


class NotebookTokens(BearerAuthentication):
    """The application's own tokens, as its authorization server would give them: here, wendy's."""

    @override
    def authenticate(self, token: str) -> Principal | None:
        return Principal("wendy", frozenset({"writer"})) if token == "wendy-token" else None
