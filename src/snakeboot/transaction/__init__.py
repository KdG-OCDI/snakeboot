"""Technical library that declares transaction boundaries without knowing the technology."""

from snakeboot.transaction.after_commit import after_commit
from snakeboot.transaction.transaction_manager import TransactionManager
from snakeboot.transaction.transaction_manager_not_installed_error import (
    TransactionManagerNotInstalledError,
)
from snakeboot.transaction.transaction_manager_registry import TransactionManagerRegistry
from snakeboot.transaction.transactional import transactional

__all__ = [
    "TransactionManager",
    "TransactionManagerNotInstalledError",
    "TransactionManagerRegistry",
    "after_commit",
    "transactional",
]
