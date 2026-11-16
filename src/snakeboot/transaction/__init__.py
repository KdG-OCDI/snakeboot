"""Technical library that declares transaction boundaries without knowing the technology."""

from snakeboot.transaction.after_commit import after_commit
from snakeboot.transaction.transaction_definition import (
    Isolation,
    Propagation,
    TransactionDefinition,
    TransactionPhase,
)
from snakeboot.transaction.transaction_errors import (
    IllegalTransactionStateError,
    ReadOnlyTransactionError,
    UnexpectedRollbackError,
)
from snakeboot.transaction.transaction_manager import DEFAULT_DEFINITION, TransactionManager
from snakeboot.transaction.transaction_manager_not_installed_error import (
    TransactionManagerNotInstalledError,
)
from snakeboot.transaction.transaction_manager_registry import TransactionManagerRegistry
from snakeboot.transaction.transaction_synchronizations import TransactionSynchronizations, run_robustly
from snakeboot.transaction.transactional import transactional

__all__ = [
    "DEFAULT_DEFINITION",
    "IllegalTransactionStateError",
    "Isolation",
    "Propagation",
    "ReadOnlyTransactionError",
    "TransactionDefinition",
    "TransactionManager",
    "TransactionManagerNotInstalledError",
    "TransactionManagerRegistry",
    "TransactionPhase",
    "TransactionSynchronizations",
    "UnexpectedRollbackError",
    "after_commit",
    "run_robustly",
    "transactional",
]
