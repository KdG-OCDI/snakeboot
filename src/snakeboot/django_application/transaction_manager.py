from snakeboot.django import DjangoAtomicTransactionManager
from snakeboot.transaction import TransactionManagerRegistry


def install_transaction_manager(settings: object) -> None:
    """Lets `@transactional` run on Django's `transaction.atomic` when the service has a database.

    Without DATABASES nothing is installed, so a `@transactional` call in a service without a database fails with a
    clear message instead of opening a transaction on nothing.
    """
    if getattr(settings, "DATABASES", None):
        TransactionManagerRegistry.install(DjangoAtomicTransactionManager())
