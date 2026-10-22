"""Django integration: runs `@transactional` on Django's `transaction.atomic` (extra: `snakeboot[django]`)."""

from snakeboot.django.django_atomic_transaction_manager import DjangoAtomicTransactionManager

__all__ = ["DjangoAtomicTransactionManager"]
