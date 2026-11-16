from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Final

from sqlalchemy import URL, Engine, create_engine, text
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session, sessionmaker

from snakeboot.configuration import DatabaseProperties
from snakeboot.sqlalchemy_data.data_access_errors import translated_errors
from snakeboot.sqlalchemy_data.persistence_context import hold_what_is_loaded
from snakeboot.sqlalchemy_data.persistence_lifecycle import READ_ONLY, audit_and_guard_every_flush
from snakeboot.sqlalchemy_data.sqlite import sqlite_file_engine
from snakeboot.transaction import (
    DEFAULT_DEFINITION,
    IllegalTransactionStateError,
    Isolation,
    Propagation,
    TransactionDefinition,
    TransactionPhase,
    TransactionSynchronizations,
    UnexpectedRollbackError,
)

CONNECT_TIMEOUT_SECONDS: Final = 10
"""How long connecting to the PostgreSQL server may take, like the `connectTimeout` of PostgreSQL's JDBC driver.

Without it psycopg waits 130 seconds per address of the host, and on Windows even a refused connection fails only
then: over four minutes for `localhost` before `migrate` or the start says the server is not running."""


@dataclass
class _Transaction:
    """The session of a physical transaction, and what it waits for: its callbacks, and whether it must roll back."""

    session: Session
    synchronizations: TransactionSynchronizations = field(default_factory=TransactionSynchronizations)


class Database:
    """The database of the application: SQLAlchemy's engine, and the session of the transaction that runs now.

    Like Spring's `EntityManager` bound to a transaction, with the propagation of Spring's `JpaTransactionManager`:
    `transaction()` opens a session and its transaction, or joins the one that runs (`REQUIRED`), opens a savepoint in
    it (`NESTED`) or suspends it for one of its own (`REQUIRES_NEW`); `session()` hands the repositories the session of
    the running transaction, or runs their work in a transaction of its own. An exception that leaves a joined block
    marks the transaction rollback-only: it then rolls back at its end, and raises `UnexpectedRollbackError` when its
    own block ended without one. The session lives in a context variable, so each thread, and each
    task of an event loop, has its own. Like JPA's persistence context, a transaction's session holds every entity it
    read until the transaction ends: a repository hands out one object per row, as the row was first read, so a
    `Version()` is checked against the version this transaction read. Entities stay readable after the commit: the
    session does not expire them. Every flush fills the audit fields of the entities it writes.
    SQLAlchemy's errors of data access leave both in snakeboot's terms (`OptimisticLockingFailureError`,
    `DataIntegrityViolationError`).

    The callbacks after the end run once the session closed and the context is cleared: a repository call in one runs
    in a transaction of its own, which commits by itself.
    """

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._sessions = sessionmaker(engine, expire_on_commit=False)
        hold_what_is_loaded(self._sessions)
        audit_and_guard_every_flush(self._sessions)
        self._running: ContextVar[_Transaction | None] = ContextVar(f"snakeboot-transaction-{id(self)}", default=None)

    @classmethod
    def of(cls, properties: DatabaseProperties) -> "Database":
        """Returns the database of `[database]`: its SQLite file, or its PostgreSQL server, whose pool tests a
        connection before it lends it and gives up connecting after `CONNECT_TIMEOUT_SECONDS`."""
        if properties.file is not None:
            return cls(sqlite_file_engine(properties.file))
        url = URL.create(
            "postgresql+psycopg",
            username=properties.user,
            password=properties.password.get_secret_value() if properties.password is not None else None,
            host=properties.host,
            port=properties.port,
            database=properties.name,
        )
        return cls(create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS}))

    @property
    def in_transaction(self) -> bool:
        """Tells whether a transaction runs in this context."""
        return self._running.get() is not None

    @property
    def offers_independent_transactions(self) -> bool:
        """Tells whether a transaction may run beside a suspended one (`REQUIRES_NEW`): not on SQLite, whose one
        writer would wait for the suspended transaction, nor on the one shared connection of a test's database."""
        return self.engine.dialect.name != "sqlite"

    @contextmanager
    def transaction(self, definition: TransactionDefinition = DEFAULT_DEFINITION) -> Iterator[Session]:
        """Runs the block in a transaction as `definition` asks: commits when a transaction it started ends, rolls back
        when the block raises; inside a running transaction, joins it, opens a savepoint or suspends it."""
        running = self._running.get()
        if running is None:
            yield from self._outermost(definition)
        elif definition.propagation is Propagation.REQUIRES_NEW:
            yield from self._independent(definition)
        else:
            _refuse_isolation_of_a_running_transaction(definition)
            if definition.propagation is Propagation.NESTED:
                yield from _savepoint(running, definition)
            else:
                yield from _joined(running, definition)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Returns the session of the running transaction, or runs the block in a transaction of its own."""
        with self.transaction() as session:
            yield session

    def register(self, phase: TransactionPhase, callback: Callable[[], None]) -> None:
        """Runs `callback` in `phase` of the running transaction; outside one, refuses."""
        running = self._running.get()
        if running is None:
            raise IllegalTransactionStateError(f"No transaction runs, so there is no {phase} to wait for.")
        running.synchronizations.register(phase, callback)

    def flush(self) -> None:
        """Writes the pending changes of the running transaction; outside a transaction nothing is pending."""
        running = self._running.get()
        if running is not None:
            with translated_errors():
                running.session.flush()

    def close(self) -> None:
        """Closes every connection of the pool."""
        self.engine.dispose()

    def _outermost(self, definition: TransactionDefinition) -> Generator[Session]:
        running: _Transaction | None = None
        surviving: BaseException | None = None
        try:
            with translated_errors(), self._sessions() as session, session.begin():
                running = _Transaction(session)
                self._prepare(session, definition)
                token = self._running.set(running)
                try:
                    surviving = yield from _guarded(session, definition)
                    running.synchronizations.before_commit()
                    _refuse_to_commit_what_must_roll_back(running)
                finally:
                    self._running.reset(token)
        except BaseException:
            if running is not None:
                running.synchronizations.after_completion(committed=False)
            raise
        if running is not None:
            running.synchronizations.after_completion(committed=True)
        if surviving is not None:
            raise surviving

    def _independent(self, definition: TransactionDefinition) -> Generator[Session]:
        if not self.offers_independent_transactions:
            raise IllegalTransactionStateError(
                f"Propagation.REQUIRES_NEW needs a second, independent transaction, which {self.engine.dialect.name} "
                "cannot run beside the suspended one. Use PostgreSQL (in a test: "
                "@application_test(database=PostgreSQLContainer())), or Propagation.NESTED for a savepoint."
            )
        token = self._running.set(None)
        try:
            yield from self._outermost(definition)
        finally:
            self._running.reset(token)

    def _prepare(self, session: Session, definition: TransactionDefinition) -> None:
        session.info[READ_ONLY] = definition.read_only
        if definition.isolation is not Isolation.DEFAULT:
            try:
                session.connection(execution_options={"isolation_level": definition.isolation.value})
            except ArgumentError as error:
                raise IllegalTransactionStateError(
                    f"{self.engine.dialect.name} offers no isolation {definition.isolation.value}: {error}"
                ) from error
        if definition.read_only and self.engine.dialect.name == "postgresql":
            session.execute(text("SET TRANSACTION READ ONLY"))


def _guarded(session: Session, definition: TransactionDefinition) -> Generator[Session, None, BaseException | None]:
    """Yields the session; returns the exception of the block that does not roll back, and re-raises the others."""
    try:
        yield session
    except BaseException as error:
        if definition.rolls_back_on(error):
            raise
        return error
    return None


def _joined(running: _Transaction, definition: TransactionDefinition) -> Generator[Session]:
    try:
        with translated_errors():
            yield running.session
    except BaseException as error:
        if definition.rolls_back_on(error):
            running.synchronizations.rollback_only = True
        raise


def _savepoint(running: _Transaction, definition: TransactionDefinition) -> Generator[Session]:
    running.synchronizations.begin_savepoint()
    try:
        with translated_errors(), running.session.begin_nested():
            surviving = yield from _guarded(running.session, definition)
    except BaseException:
        running.synchronizations.rollback_savepoint()
        raise
    running.synchronizations.release_savepoint()
    if surviving is not None:
        raise surviving


def _refuse_isolation_of_a_running_transaction(definition: TransactionDefinition) -> None:
    if definition.isolation is not Isolation.DEFAULT:
        raise IllegalTransactionStateError(
            "A call that joins the running transaction keeps its isolation; it cannot ask "
            f"{definition.isolation.value}. Ask it of the outermost @transactional call, or use "
            "Propagation.REQUIRES_NEW."
        )


def _refuse_to_commit_what_must_roll_back(running: _Transaction) -> None:
    if running.synchronizations.rollback_only:
        raise UnexpectedRollbackError(
            "The transaction rolled back: a @transactional call that joined it failed, and its caller went on. "
            "Use Propagation.NESTED for a call whose failure the caller may survive."
        )
