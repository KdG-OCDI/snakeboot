from typing import Final

from sqlalchemy import event
from sqlalchemy.orm import Session, UOWTransaction, sessionmaker

from snakeboot.data.auditing import audit
from snakeboot.transaction import ReadOnlyTransactionError

READ_ONLY: Final = "snakeboot_read_only"
"""The key of `Session.info` that tells whether the session's transaction is `@transactional(read_only=True)`."""


def audit_and_guard_every_flush(sessions: sessionmaker[Session]) -> None:
    """Makes every flush of `sessions` fill the audit fields of what it writes, and refuse to write when read-only.

    Like JPA's `@PrePersist` and `@PreUpdate` with Spring Data's `AuditingEntityListener`: an entity a transaction
    loaded and changed is written at the flush without a `save`, and its `LastModifiedBy` and `LastModifiedDate` are
    filled then, in the same flush and the same transaction as its data. An entity whose fields did not change is not
    written, and keeps its audit fields. A native `@query` that changes rows is no entity's write: it is not audited.
    """
    event.listen(sessions, "before_flush", _before_flush)


def _before_flush(session: Session, _flush: UOWTransaction, _instances: object) -> None:
    changed = [entity for entity in session.dirty if session.is_modified(entity)]
    if session.info.get(READ_ONLY) and (session.new or changed or session.deleted):
        raise ReadOnlyTransactionError(
            "A @transactional(read_only=True) transaction is about to write a changed entity; read-only transactions "
            "write nothing."
        )
    for entity in (*session.new, *changed):
        audit(entity)
