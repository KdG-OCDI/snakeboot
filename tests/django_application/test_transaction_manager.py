"""With a database, `@transactional` runs on Django's `transaction.atomic`; without one, nothing is installed."""

from collections.abc import Iterator
from types import SimpleNamespace

import pytest

from snakeboot.django import DjangoAtomicTransactionManager
from snakeboot.django_application.transaction_manager import install_transaction_manager
from snakeboot.transaction import TransactionManagerNotInstalledError, TransactionManagerRegistry


@pytest.fixture(autouse=True)
def no_installed_manager() -> Iterator[None]:
    TransactionManagerRegistry.uninstall()
    yield
    TransactionManagerRegistry.uninstall()


def test_with_a_database_the_django_transaction_manager_is_installed() -> None:
    install_transaction_manager(SimpleNamespace(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3"}}))

    assert isinstance(TransactionManagerRegistry.current(), DjangoAtomicTransactionManager)


@pytest.mark.parametrize("settings", [SimpleNamespace(DATABASES={}), SimpleNamespace()])
def test_without_a_database_nothing_is_installed(settings: SimpleNamespace) -> None:
    install_transaction_manager(settings)

    with pytest.raises(TransactionManagerNotInstalledError):
        TransactionManagerRegistry.current()
