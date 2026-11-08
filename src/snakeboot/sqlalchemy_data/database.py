import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from snakeboot.configuration import DatabaseProperties

logger = logging.getLogger(__name__)


@dataclass
class _Transaction:
    """The session of the outermost transaction, and the callbacks waiting for its commit, one list per savepoint."""

    session: Session
    waiting: list[list[Callable[[], None]]] = field(default_factory=lambda: [[]])


class Database:
    """The database of the application: SQLAlchemy's engine, and the session of the transaction that runs now.

    Like Spring's `EntityManager` bound to a transaction: `transaction()` opens a session and its transaction, or a
    savepoint inside the one that runs; `session()` hands the repositories the session of the running transaction, or
    runs their work in a transaction of its own. The session lives in a context variable, so each thread, and each
    task of an event loop, has its own. Entities stay readable after the commit: the session does not expire them.
    """

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._sessions = sessionmaker(engine, expire_on_commit=False)
        self._running: ContextVar[_Transaction | None] = ContextVar(f"snakeboot-transaction-{id(self)}", default=None)

    @classmethod
    def of(cls, properties: DatabaseProperties) -> "Database":
        """Returns the PostgreSQL database of `[database]`, whose pool tests a connection before it lends it."""
        url = URL.create(
            "postgresql+psycopg",
            username=properties.user,
            password=properties.password.get_secret_value(),
            host=properties.host,
            port=properties.port,
            database=properties.name,
        )
        return cls(create_engine(url, pool_pre_ping=True))

    @property
    def in_transaction(self) -> bool:
        """Tells whether a transaction runs in this context."""
        return self._running.get() is not None

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        """Commits when the block ends and rolls back when it raises; inside a running transaction, a savepoint."""
        running = self._running.get()
        if running is None:
            yield from self._outermost()
        else:
            yield from self._savepoint(running)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Returns the session of the running transaction, or runs the block in a transaction of its own."""
        running = self._running.get()
        if running is not None:
            yield running.session
        else:
            with self.transaction() as session:
                yield session

    def on_commit(self, callback: Callable[[], None]) -> None:
        """Runs `callback` once the outermost transaction has committed, or at once outside a transaction."""
        running = self._running.get()
        if running is None:
            _run_robustly(callback)
        else:
            running.waiting[-1].append(callback)

    def close(self) -> None:
        """Closes every connection of the pool."""
        self.engine.dispose()

    def _outermost(self) -> Iterator[Session]:
        with self._sessions() as session, session.begin():
            running = _Transaction(session)
            token = self._running.set(running)
            try:
                yield session
            finally:
                self._running.reset(token)
        for callback in running.waiting[0]:
            _run_robustly(callback)

    def _savepoint(self, running: _Transaction) -> Iterator[Session]:
        running.waiting.append([])
        try:
            with running.session.begin_nested():
                yield running.session
        except BaseException:
            running.waiting.pop()
            raise
        committed = running.waiting.pop()
        running.waiting[-1].extend(committed)


def _run_robustly(callback: Callable[[], None]) -> None:
    # Like Spring's TransactionSynchronization.afterCommit: the transaction has committed, so a failing callback
    # must not hide that, nor stop the callbacks after it.
    try:
        callback()
    except Exception:
        logger.exception("A callback after the commit failed")
