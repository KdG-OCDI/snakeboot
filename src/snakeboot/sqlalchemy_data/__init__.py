"""The data library on SQLAlchemy: entities, repositories, transactions and migrations (extra: snakeboot[data]).

The one place that knows SQLAlchemy and Alembic. `Database` holds the engine and the session of the running
transaction; `SqlAlchemyTransactionManager` runs `@transactional` on it. An application never sees either: its
entities and repositories are `snakeboot.data`'s, and another persistence framework would get a binding like this one.
"""

from snakeboot.sqlalchemy_data.database import Database
from snakeboot.sqlalchemy_data.sqlalchemy_transaction_manager import SqlAlchemyTransactionManager

__all__ = ["Database", "SqlAlchemyTransactionManager"]
