import dataclasses
import inspect
import typing
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar, Final, Union, get_args, get_origin

from snakeboot.data.data_errors import EmptyResultError, IncorrectResultSizeError, InvalidRepositoryError
from snakeboot.data.derived_query import Action, Condition, DerivedQuery, Operator, derive_query
from snakeboot.data.entity import CreatedBy, CreatedDate, EntityDescription, LastModifiedBy, LastModifiedDate
from snakeboot.data.query_methods import LOCK_ATTRIBUTE, QUERY_ATTRIBUTE
from snakeboot.data.repository_operations import NativeQuery, PageRequest, QueryCall, RepositoryOperations
from snakeboot.security import SecurityContext

_EVERYTHING: Final = DerivedQuery(Action.FIND, alternatives=(), ordering=(), limit=None)


class Cardinality(StrEnum):
    """How many results a method returns, read from its return annotation."""

    MANY = "many"
    """`list[E]`, `Sequence[E]`, `tuple[E, ...]`: every result."""
    OPTIONAL = "optional"
    """`E | None`: the one result, or None; several stop the call."""
    ONE = "one"
    """`E`: the one result; none or several stop the call."""


class RepositoryImplementation:
    """The methods of `CrudRepository`, which every implementation of a repository interface inherits."""

    _entity: ClassVar[EntityDescription]

    def __init__(self, operations: RepositoryOperations) -> None:
        self._operations = operations

    def save(self, entity: Any) -> Any:
        """Fills the audit dates and auditors, then inserts or updates `entity`."""
        return self._operations.save(_audited(self._entity, entity))

    def save_all(self, entities: Iterable[Any]) -> list[Any]:
        """Saves every entity in order."""
        return [self.save(entity) for entity in entities]

    def find_by_id(self, identifier: Any) -> Any:
        """Returns the entity with `identifier`, or None."""
        return _one_of(self._operations.find(self._by_id(identifier)), Cardinality.OPTIONAL)

    def exists_by_id(self, identifier: Any) -> bool:
        """Tells whether an entity has `identifier`."""
        return self._operations.exists(self._by_id(identifier))

    def find_all(self) -> list[Any]:
        """Returns every entity."""
        return self._operations.find(QueryCall(self._entity, _EVERYTHING, ()))

    def count(self) -> int:
        """Returns how many entities there are."""
        return self._operations.count(QueryCall(self._entity, _EVERYTHING, ()))

    def delete(self, entity: Any) -> None:
        """Deletes `entity`."""
        self._operations.delete(entity)

    def delete_by_id(self, identifier: Any) -> None:
        """Deletes the entity with `identifier`, if there is one."""
        self._operations.delete_where(self._by_id(identifier))

    def delete_all(self) -> None:
        """Deletes every entity."""
        self._operations.delete_where(QueryCall(self._entity, _EVERYTHING, ()))

    def _by_id(self, identifier: Any) -> QueryCall:
        by_id = Condition(self._entity.identifier.name, Operator.EQUALS)
        return QueryCall(self._entity, dataclasses.replace(_EVERYTHING, alternatives=((by_id,),)), (identifier,))


def implemented_methods(
    entity: EntityDescription, declared: Mapping[str, Callable[..., Any]]
) -> dict[str, Callable[..., Any]]:
    """Returns an implementation of every method `declared` beyond CrudRepository's, by name."""
    return {
        name: _native_method(method) if hasattr(method, QUERY_ATTRIBUTE) else _derived_method(entity, method)
        for name, method in declared.items()
        if not hasattr(RepositoryImplementation, name) or hasattr(method, QUERY_ATTRIBUTE)
    }


def _derived_method(entity: EntityDescription, method: Callable[..., Any]) -> Callable[..., Any]:
    name = method.__name__
    query = derive_query(name, [prop.name for prop in entity.properties])
    parameters, returned = _parameters_and_return(method)
    paged = bool(parameters) and parameters[-1].annotation is PageRequest
    if len(parameters) - paged != query.arity:
        raise InvalidRepositoryError(
            f"{name} takes {len(parameters) - paged} arguments for its conditions, but its name asks for {query.arity}."
        )
    run = _runner_of(entity, query, name=name, returned=returned)
    lock, signature = getattr(method, LOCK_ATTRIBUTE, None), inspect.Signature(parameters)

    def derived(self: RepositoryImplementation, *arguments: Any, **keywords: Any) -> Any:
        values = tuple(_bound(signature, arguments, keywords).values())
        page, conditions = (values[-1], values[:-1]) if paged else (None, values)
        return run(self._operations, QueryCall(entity, query, conditions, page, lock))  # reason: own

    derived.__name__ = derived.__qualname__ = name
    return derived


def _runner_of(
    entity: EntityDescription, query: DerivedQuery, *, name: str, returned: Any
) -> Callable[[RepositoryOperations, QueryCall], Any]:
    match query.action:
        case Action.COUNT:
            _expect(returned in {int}, name, "a count_by method returns int")
            return lambda operations, call: operations.count(call)
        case Action.EXISTS:
            _expect(returned in {bool}, name, "an exists_by method returns bool")
            return lambda operations, call: operations.exists(call)
        case Action.DELETE:
            _expect(returned in {int, None, type(None)}, name, "a delete_by method returns int or None")
            return lambda operations, call: operations.delete_where(call)
        case Action.FIND:
            cardinality, element = _cardinality_of(returned)
            _expect(element is entity.entity_type, name, f"a find_by method returns {entity.entity_type.__name__}s")
            return lambda operations, call: _one_of(operations.find(call), cardinality)


def _native_method(method: Callable[..., Any]) -> Callable[..., Any]:
    declared: NativeQuery = getattr(method, QUERY_ATTRIBUTE)
    parameters, returned = _parameters_and_return(method)
    signature = inspect.Signature(parameters)
    if declared.modifying:
        _expect(returned in {int, None, type(None)}, method.__name__, "a modifying @query returns int or None")

        def modifying(self: RepositoryImplementation, *arguments: Any, **keywords: Any) -> int:
            return self._operations.update(declared, _bound(signature, arguments, keywords))  # reason: own

        return _named(modifying, method)
    cardinality, element = _cardinality_of(returned)
    native = dataclasses.replace(declared, result_type=element)

    def selecting(self: RepositoryImplementation, *arguments: Any, **keywords: Any) -> Any:
        named = _bound(signature, arguments, keywords)
        return _one_of(self._operations.select(native, named), cardinality)  # reason: own

    return _named(selecting, method)


def _bound(signature: inspect.Signature, arguments: tuple[Any, ...], keywords: dict[str, Any]) -> dict[str, Any]:
    bound = signature.bind(*arguments, **keywords)
    bound.apply_defaults()
    return dict(bound.arguments)


def _named(implementation: Callable[..., Any], method: Callable[..., Any]) -> Callable[..., Any]:
    implementation.__name__ = implementation.__qualname__ = method.__name__
    return implementation


def _parameters_and_return(method: Callable[..., Any]) -> tuple[list[inspect.Parameter], Any]:
    try:
        hints = typing.get_type_hints(method)
    except NameError as error:
        raise InvalidRepositoryError(f"{method.__name__} names a type snakeboot cannot find: {error}") from error
    parameters = [
        parameter.replace(annotation=hints.get(name, parameter.annotation))
        for name, parameter in inspect.signature(method).parameters.items()
        if name != "self"
    ]
    if "return" not in hints:
        raise InvalidRepositoryError(f"{method.__name__} has no return annotation: it says what the method returns.")
    return parameters, hints["return"]


def _cardinality_of(annotation: Any) -> tuple[Cardinality, Any]:
    origin = get_origin(annotation)
    if origin in {list, tuple, Sequence, Collection, Iterable}:
        return Cardinality.MANY, get_args(annotation)[0]
    if origin is Union or (origin is not None and type(None) in get_args(annotation)):
        others = [argument for argument in get_args(annotation) if argument is not type(None)]
        return Cardinality.OPTIONAL, others[0] if len(others) == 1 else annotation
    return Cardinality.ONE, annotation


def _one_of(results: list[Any], cardinality: Cardinality) -> Any:
    if cardinality is Cardinality.MANY:
        return results
    if len(results) > 1:
        raise IncorrectResultSizeError(f"Expected one result, found {len(results)}.")
    if not results and cardinality is Cardinality.ONE:
        raise EmptyResultError("Expected one result, found none.")
    return results[0] if results else None


def _audited(entity: EntityDescription, value: Any) -> Any:
    # Like Spring Data's AuditingHandler: the creation once, the last modification on every save.
    now, principal = datetime.now(UTC), SecurityContext.current()
    auditor = principal.name if principal is not None else None
    for prop in entity.properties:
        empty = getattr(value, prop.name) is None
        if prop.marker(LastModifiedDate) is not None or (prop.marker(CreatedDate) is not None and empty):
            setattr(value, prop.name, now)
        elif prop.marker(LastModifiedBy) is not None or (prop.marker(CreatedBy) is not None and empty):
            setattr(value, prop.name, auditor)
    return value


def _expect(fits: bool, name: str, rule: str) -> None:  # noqa: FBT001  # reason: a check reads as a sentence
    if not fits:
        raise InvalidRepositoryError(f"{name}: {rule}.")
