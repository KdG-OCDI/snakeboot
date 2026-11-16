class UnexpectedRollbackError(RuntimeError):
    """Raised when a transaction that was to commit rolled back instead, like Spring's `UnexpectedRollbackException`.

    A `@transactional` call that joined the transaction failed, and its caller caught the exception and went on: the
    shared transaction was marked rollback-only, so none of its work commits. Choose `Propagation.NESTED` for a call
    whose failure the caller may survive.
    """


class IllegalTransactionStateError(RuntimeError):
    """Raised when a transaction cannot be what a call asks of it, like Spring's `IllegalTransactionStateException`.

    An isolation for a call that joins a running transaction, `Propagation.REQUIRES_NEW` on a database without
    independent connections, or a transaction callback outside a transaction.
    """


class ReadOnlyTransactionError(IllegalTransactionStateError):
    """Raised when a `@transactional(read_only=True)` transaction is about to write a changed entity."""
