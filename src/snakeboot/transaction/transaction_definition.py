from dataclasses import dataclass
from enum import StrEnum


class Propagation(StrEnum):
    """How a `@transactional` call relates to a transaction that already runs, like Spring's `Propagation`."""

    REQUIRED = "required"
    """Joins the running transaction, or starts one (the default). An exception that leaves the call marks the shared
    transaction rollback-only: catching it further up does not save the transaction, which then rolls back at its end
    and raises `UnexpectedRollbackError`."""
    NESTED = "nested"
    """Runs in a savepoint of the running transaction, or starts one: an exception that leaves the call undoes only the
    call's own work, and the caller may go on. A savepoint is not a commit: the work still rolls back with the outer
    transaction."""
    REQUIRES_NEW = "requires_new"
    """Suspends the running transaction and runs in an independent one, on a connection of its own: it commits or rolls
    back by itself, whatever the outer transaction does later. Needs a database with independent connections
    (PostgreSQL); SQLite refuses it."""


class Isolation(StrEnum):
    """The isolation level of a new transaction, like Spring's `Isolation`; the database decides which it offers."""

    DEFAULT = "DEFAULT"
    """The database's own default (READ COMMITTED on PostgreSQL)."""
    READ_UNCOMMITTED = "READ UNCOMMITTED"
    """May read changes other transactions have not committed (PostgreSQL treats it as READ COMMITTED)."""
    READ_COMMITTED = "READ COMMITTED"
    """Reads only committed changes; a second read may see another transaction's newer commit."""
    REPEATABLE_READ = "REPEATABLE READ"
    """Reads the same rows the same way for the whole transaction."""
    SERIALIZABLE = "SERIALIZABLE"
    """As if the transactions ran one after the other; a conflict fails one of them."""


class TransactionPhase(StrEnum):
    """When a callback of a transaction runs, like Spring's `TransactionPhase`."""

    BEFORE_COMMIT = "before_commit"
    """Inside the transaction, just before it commits: its writes commit with it, its failure rolls it back."""
    AFTER_COMMIT = "after_commit"
    """Once the transaction committed (the default of a transactional event listener)."""
    AFTER_ROLLBACK = "after_rollback"
    """Once the transaction rolled back."""
    AFTER_COMPLETION = "after_completion"
    """Once the transaction ended, committed or rolled back."""


@dataclass(frozen=True, slots=True)
class TransactionDefinition:
    """What a `@transactional` call asks of its transaction, like Spring's `TransactionDefinition`.

    `isolation` and `read_only` apply to a transaction the call starts; a call that joins one keeps the running
    transaction's, and asking an isolation then is refused (`IllegalTransactionStateError`). `no_rollback_for` names the
    exceptions that leave the call without rolling back: the transaction commits and the exception still reaches the
    caller. Every other exception rolls back: Python has no checked exceptions, so there is no counterpart of Spring's
    rule that only a `RuntimeException` rolls back.
    """

    propagation: Propagation = Propagation.REQUIRED
    isolation: Isolation = Isolation.DEFAULT
    read_only: bool = False
    no_rollback_for: tuple[type[BaseException], ...] = ()

    def rolls_back_on(self, error: BaseException) -> bool:
        """Tells whether `error`, leaving the call, rolls the transaction back."""
        return not isinstance(error, self.no_rollback_for)
