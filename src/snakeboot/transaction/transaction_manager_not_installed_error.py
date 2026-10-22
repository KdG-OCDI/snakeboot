class TransactionManagerNotInstalledError(RuntimeError):
    """Raised when `@transactional` runs before composition installed a TransactionManager.

    A missing manager is a wiring mistake. Failing loudly prevents a use case from
    silently changing state without a transaction.
    """
