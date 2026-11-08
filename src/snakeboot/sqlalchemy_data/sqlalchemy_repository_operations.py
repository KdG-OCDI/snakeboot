from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final, override
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, delete, func, or_, select, text, true
from sqlalchemy.engine import CursorResult

from snakeboot.data import (
    ENTITY_ATTRIBUTE,
    Condition,
    LockMode,
    NativeQuery,
    Operator,
    QueryCall,
    RepositoryOperations,
)
from snakeboot.sqlalchemy_data.database import Database
from snakeboot.sqlalchemy_data.entity_mapping import EntityMapping

_SCALARS: Final = {int, str, float, bool, Decimal, UUID, datetime, date, bytes}

_COMPARISONS: Final[dict[Operator, Callable[[ColumnElement[Any], Sequence[Any]], ColumnElement[bool]]]] = {
    Operator.EQUALS: lambda column, values: column == values[0],
    Operator.NOT: lambda column, values: column != values[0],
    Operator.LESS_THAN: lambda column, values: column < values[0],
    Operator.LESS_THAN_EQUAL: lambda column, values: column <= values[0],
    Operator.GREATER_THAN: lambda column, values: column > values[0],
    Operator.GREATER_THAN_EQUAL: lambda column, values: column >= values[0],
    Operator.BETWEEN: lambda column, values: column.between(values[0], values[1]),
    Operator.IN: lambda column, values: column.in_(list(values[0])),
    Operator.NOT_IN: lambda column, values: column.not_in(list(values[0])),
    Operator.IS_NULL: lambda column, _: column.is_(None),
    Operator.IS_NOT_NULL: lambda column, _: column.is_not(None),
    Operator.LIKE: lambda column, values: column.like(values[0]),
    Operator.NOT_LIKE: lambda column, values: column.not_like(values[0]),
    Operator.STARTING_WITH: lambda column, values: column.startswith(values[0], autoescape=True),
    Operator.ENDING_WITH: lambda column, values: column.endswith(values[0], autoescape=True),
    Operator.CONTAINING: lambda column, values: column.contains(values[0], autoescape=True),
    Operator.TRUE: lambda column, _: column.is_(True),
    Operator.FALSE: lambda column, _: column.is_(False),
}


class SqlAlchemyRepositoryOperations(RepositoryOperations):
    """Runs the repositories of `snakeboot.data` on SQLAlchemy, in the session of the running transaction.

    Every call joins the running transaction, or runs in one of its own, as Spring Data's repositories are
    transactional. `save` is SQLAlchemy's `merge`: an UPDATE for an identifier the table has, an INSERT otherwise.
    """

    def __init__(self, database: Database, mapping: EntityMapping) -> None:
        self._database = database
        self._mapping = mapping

    @override
    def save(self, entity: Any) -> Any:
        self._mapping.table(type(entity))
        with self._database.session() as session:
            saved = session.merge(entity)
            session.flush()
            return saved

    @override
    def delete(self, entity: Any) -> None:
        with self._database.session() as session:
            session.delete(session.merge(entity))

    @override
    def find(self, call: QueryCall) -> list[Any]:
        statement: Select[Any] = self._ordered(call, select(call.entity.entity_type).where(self._where(call)))
        if call.lock is not None:
            statement = statement.with_for_update(read=call.lock is LockMode.PESSIMISTIC_READ)
        with self._database.session() as session:
            return list(session.scalars(statement))

    @override
    def count(self, call: QueryCall) -> int:
        table = self._mapping.table(call.entity.entity_type)
        with self._database.session() as session:
            return session.scalar(select(func.count()).select_from(table).where(self._where(call))) or 0

    @override
    def exists(self, call: QueryCall) -> bool:
        table = self._mapping.table(call.entity.entity_type)
        with self._database.session() as session:
            return bool(session.scalar(select(select(table).where(self._where(call)).exists())))

    @override
    def delete_where(self, call: QueryCall) -> int:
        statement = delete(call.entity.entity_type).where(self._where(call))
        with self._database.session() as session:
            result = session.execute(statement)
            return result.rowcount if isinstance(result, CursorResult) else 0

    @override
    def select(self, query: NativeQuery, arguments: Mapping[str, Any]) -> list[Any]:
        statement, result_type = text(query.sql), query.result_type
        with self._database.session() as session:
            if isinstance(result_type, type) and ENTITY_ATTRIBUTE in vars(result_type):
                return list(session.scalars(select(result_type).from_statement(statement), dict(arguments)))
            if result_type in _SCALARS:
                return list(session.scalars(statement, dict(arguments)))
            return [result_type(**row) for row in session.execute(statement, dict(arguments)).mappings()]

    @override
    def update(self, query: NativeQuery, arguments: Mapping[str, Any]) -> int:
        with self._database.session() as session:
            result = session.execute(text(query.sql), dict(arguments))
            return result.rowcount if isinstance(result, CursorResult) else 0

    def _where(self, call: QueryCall) -> ColumnElement[bool]:
        table = self._mapping.table(call.entity.entity_type)
        arguments = iter(call.arguments)

        def compared(condition: Condition) -> ColumnElement[bool]:
            values = [next(arguments) for _ in range(condition.operator.arity)]
            return _COMPARISONS[condition.operator](table.c[condition.field], values)

        alternatives = [
            and_(*(compared(condition) for condition in conditions)) for conditions in call.query.alternatives
        ]
        return or_(*alternatives) if alternatives else true()

    def _ordered[S: Select[Any]](self, call: QueryCall, statement: S) -> S:
        table = self._mapping.table(call.entity.entity_type)
        keys = [
            table.c[key.field].desc() if key.descending else table.c[key.field].asc() for key in call.query.ordering
        ]
        ordered = statement.order_by(*keys)
        if call.query.limit is not None:
            ordered = ordered.limit(call.query.limit)
        if call.page is not None:
            ordered = ordered.offset(call.page.offset).limit(call.page.limit)
        return ordered
