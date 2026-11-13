"""A table of its own, a listener that needs no outbox, and a scheduled method without a lock."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

from snakeboot.data import Id, entity
from snakeboot.events import application_event_listener, event_listener, transactional_event_listener
from snakeboot.scheduling import scheduled


@entity("plain_note")
@dataclass
class NoteRecord:
    note_id: Annotated[int, Id()]
    text: str


@application_event_listener
class NoteListener:
    @event_listener(NoteRecord)
    def at_once(self, event: NoteRecord) -> None:
        """Hears a note inside the publisher's transaction."""

    @transactional_event_listener(NoteRecord)
    def after_the_commit(self, event: NoteRecord) -> None:
        """Hears a note after the commit, without the outbox."""


class NoteSweeper:
    @scheduled(fixed_rate=timedelta(minutes=1))
    def sweep(self) -> None:
        """Runs on every replica: no lock."""
