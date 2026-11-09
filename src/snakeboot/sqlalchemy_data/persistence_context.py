from typing import Final

from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

_HELD: Final = "snakeboot_held"
"""The key of `Session.info` under which a session keeps every entity it loaded or saved, by identity."""


def hold_what_is_loaded(sessions: sessionmaker[Session]) -> None:
    """Makes every session of `sessions` hold its entities until it ends, as JPA's persistence context does.

    SQLAlchemy's identity map holds an entity only as long as somebody else does. An adapter that maps a record to its
    domain object and lets the record go would read the row afresh at its next query, with a version written meanwhile
    by another transaction, and a `Version()` field would never catch the lost update. Held here, the row stays as
    this transaction first read it, until the transaction ends.
    """
    for became_persistent in ("loaded_as_persistent", "pending_to_persistent", "detached_to_persistent"):
        event.listen(sessions, became_persistent, _hold)
    for left in ("persistent_to_detached", "persistent_to_deleted", "persistent_to_transient"):
        event.listen(sessions, left, _let_go)


def _hold(session: Session, entity: object) -> None:
    # By identity: a dataclass entity compares by value and has no hash.
    session.info.setdefault(_HELD, {})[id(entity)] = entity


def _let_go(session: Session, entity: object) -> None:
    session.info.get(_HELD, {}).pop(id(entity), None)
