import sys
from collections.abc import Callable, Iterable
from typing import Any, Final, Protocol, get_args, get_origin, override

from wireup import injectable

from snakeboot.data.data_errors import InvalidRepositoryError
from snakeboot.data.entity import description_of
from snakeboot.data.repository_implementation import RepositoryImplementation, implemented_methods

REPOSITORY_ATTRIBUTE: Final = "__snakeboot_repository__"
"""Set on every repository interface, with the class snakeboot implemented it with."""


class CrudRepository[E, ID](Protocol):
    """A repository of entities of type `E` with identifiers of type `ID`, like Spring Data's `CrudRepository`.

    Declare an interface, a Protocol that extends it; snakeboot implements it when the module is imported and makes
    the implementation the component of that interface, so an adapter asks for the interface by type:

        class GameRecords(CrudRepository[GameRecord, UUID], Protocol):
            @lock(LockMode.PESSIMISTIC_WRITE)
            def find_by_status_and_join_deadline_less_than_equal(self, status: str, deadline: datetime) -> list[
                GameRecord]: ...

            def count_by_status(self, status: str) -> int: ...

            @query("SELECT * FROM tictactoe_game WHERE board::text LIKE :pattern")
            def find_with_board_like(self, pattern: str) -> list[GameRecord]: ...

    A method is derived from its name, as in Spring Data (`find_by`, `count_by`, `exists_by`, `delete_by`, conditions
    joined by `_and_` and `_or_`, keywords such as `less_than_equal`, `in` and `is_null`, then `order_by` with `asc`
    or `desc`); its return annotation says what it returns (`list[E]`, `E | None`, `E`, `int`, `bool`). A last
    parameter of type `PageRequest` returns one page. `@query` writes the SQL itself, `@lock` locks the rows read.
    A name snakeboot cannot read stops the start.
    """

    def save(self, entity: E) -> E:
        """Inserts `entity`, or updates the row with its identifier, and returns the saved entity.

        Use the entity it returns: a number the database gives (`Id(generated=True)`) is in that one, and so are the
        audit fields. Unlike Spring Data JPA's `save`, it writes the change at once (a flush, not a commit), so a broken
        constraint or a lost update (`Version()`) is raised here, and a generated number is known; `save_and_flush`
        says so explicitly.
        """
        ...

    def save_and_flush(self, entity: E) -> E:
        """Saves `entity` and writes every pending change of the transaction now, like `JpaRepository.saveAndFlush`.

        A flush is no commit: a later rollback still undoes the change.
        """
        ...

    def save_all(self, entities: Iterable[E]) -> list[E]:
        """Saves every entity, and returns the saved ones in the same order.

        One atomic operation, like Spring Data JPA's `saveAll`: without a running transaction it runs in one of its
        own, which commits only when every entity was saved; one that fails, or an `entities` that raises while it is
        read, rolls back every change of the call. Inside a running transaction it joins it, and its failure marks
        that transaction rollback-only.
        """
        ...

    def save_all_and_flush(self, entities: Iterable[E]) -> list[E]:
        """Saves every entity, as `save_all`, and writes every pending change of the transaction now."""
        ...

    def flush(self) -> None:
        """Writes every pending change of the running transaction to the database now, like `JpaRepository.flush`.

        Changes of entities the transaction loaded are written too, with their audit fields; nothing commits.
        Outside a transaction there is nothing pending.
        """
        ...

    def find_by_id(self, identifier: ID) -> E | None:
        """Returns the entity with `identifier`, or None."""
        ...

    def exists_by_id(self, identifier: ID) -> bool:
        """Tells whether an entity has `identifier`."""
        ...

    def find_all(self) -> list[E]:
        """Returns every entity."""
        ...

    def count(self) -> int:
        """Returns how many entities there are."""
        ...

    def delete(self, entity: E) -> None:
        """Deletes `entity`."""
        ...

    def delete_by_id(self, identifier: ID) -> None:
        """Deletes the entity with `identifier`, if there is one."""
        ...

    def delete_all(self) -> None:
        """Deletes every entity."""
        ...

    @override
    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Implements an interface that extends this one, and registers the implementation as its component."""
        super().__init_subclass__(**kwargs)
        if not vars(cls).get("_is_protocol", False):
            return
        implementation = _implementation_of(cls)
        setattr(cls, REPOSITORY_ATTRIBUTE, implementation)
        # wireup registers every @injectable class among the members of a module it scans.
        setattr(sys.modules[cls.__module__], implementation.__name__, injectable(implementation, as_type=cls))


def _implementation_of(interface: type) -> type:
    entity = description_of(_entity_type_of(interface))
    methods = {
        name: method
        for owner in reversed(interface.__mro__)
        if _declares_methods(owner)
        for name, method in vars(owner).items()
        if callable(method) and not name.startswith("_")
    }
    namespace: dict[str, Callable[..., Any]] = implemented_methods(entity, methods)
    implementation = type(
        f"{interface.__name__}Implementation",
        (RepositoryImplementation, interface),
        {**namespace, "_entity": entity, "__module__": interface.__module__},
    )
    implementation.__qualname__ = implementation.__name__
    return implementation


def _declares_methods(owner: type) -> bool:
    # The interfaces between the application's and CrudRepository, whose own methods RepositoryImplementation has.
    return vars(owner).get("_is_protocol", False) and owner is not CrudRepository and CrudRepository in owner.__mro__


def _entity_type_of(interface: type) -> type:
    for owner in interface.__mro__:
        for base in vars(owner).get("__orig_bases__", ()):
            if get_origin(base) is CrudRepository:
                entity_type, _ = get_args(base)
                if isinstance(entity_type, type):
                    return entity_type
    raise InvalidRepositoryError(
        f"{interface.__name__} names no entity: extend CrudRepository[MyEntity, MyIdentifier] and Protocol."
    )
