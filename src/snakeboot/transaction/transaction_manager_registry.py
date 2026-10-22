from typing import ClassVar

from snakeboot.transaction.transaction_manager import TransactionManager
from snakeboot.transaction.transaction_manager_not_installed_error import (
    TransactionManagerNotInstalledError,
)


class TransactionManagerRegistry:
    """Holds the one TransactionManager that composition installed for this process.

    A decorator cannot receive constructor injection, so `@transactional` looks the
    manager up here. Only composition and tests call `install` and `uninstall`.
    """

    _installed: ClassVar[TransactionManager | None] = None

    @classmethod
    def install(cls, manager: TransactionManager) -> None:
        """Makes `manager` the transaction manager used by every `@transactional` call."""
        cls._installed = manager

    @classmethod
    def uninstall(cls) -> None:
        """Removes the installed manager, so a test cannot leak its manager into the next one."""
        cls._installed = None

    @classmethod
    def current(cls) -> TransactionManager:
        """Returns the installed manager or fails when composition forgot to install one."""
        if cls._installed is None:
            raise TransactionManagerNotInstalledError(
                "No TransactionManager installed. Composition must call "
                "TransactionManagerRegistry.install(...) at start-up."
            )
        return cls._installed
