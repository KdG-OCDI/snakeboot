"""Test helpers, like spring-test: a transaction manager for tests and a reader for architecture tests.

TransactionManagerRegistry.install(RecordingTransactionManager())    # use cases without a database

declared = declared_classes(Path("src/myapp"), "rest_controller")    # what the source declares
assert declared == qualified_names(urls.mounted.controllers)         # ... is what was mounted
"""

from snakeboot.testing.declared_classes import declared_classes, qualified_names
from snakeboot.testing.recording_transaction_manager import RecordingTransactionManager

__all__ = ["RecordingTransactionManager", "declared_classes", "qualified_names"]
