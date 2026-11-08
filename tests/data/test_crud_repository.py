"""snakeboot implements a repository interface when its module is imported, and stops the start when it cannot."""

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Protocol, override
from uuid import UUID, uuid4

import pytest

from snakeboot.data import (
    REPOSITORY_ATTRIBUTE,
    Action,
    CrudRepository,
    EmptyResultError,
    IncorrectResultSizeError,
    InvalidRepositoryError,
    LockMode,
    NativeQuery,
    PageRequest,
    QueryCall,
    RepositoryOperations,
)
from tests.data import sample_entities
from tests.data.sample_entities import CellCount, GameRecord, GameRecords, MoveRecord, MoveRecords

MOMENT = datetime(2026, 11, 8, 12, tzinfo=UTC)


class RecordingOperations(RepositoryOperations):
    """Stands in for a persistence framework: remembers each call and answers with what the test gives it."""

    def __init__(self, found: list[Any] | None = None) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.found = found or []

    @override
    def save(self, entity: Any) -> Any:
        self.calls.append(("save", entity))
        return entity

    @override
    def delete(self, entity: Any) -> None:
        self.calls.append(("delete", entity))

    @override
    def find(self, call: QueryCall) -> list[Any]:
        self.calls.append(("find", call))
        return self.found

    @override
    def count(self, call: QueryCall) -> int:
        self.calls.append(("count", call))
        return 7

    @override
    def exists(self, call: QueryCall) -> bool:
        self.calls.append(("exists", call))
        return True

    @override
    def delete_where(self, call: QueryCall) -> int:
        self.calls.append(("delete_where", call))
        return 2

    @override
    def select(self, query: NativeQuery, arguments: Mapping[str, Any]) -> list[Any]:
        self.calls.append(("select", (query, dict(arguments))))
        return self.found

    @override
    def update(self, query: NativeQuery, arguments: Mapping[str, Any]) -> int:
        self.calls.append(("update", (query, dict(arguments))))
        return 3


def implementation_of[R](interface: Callable[..., R], operations: RepositoryOperations) -> R:
    implementation: R = getattr(interface, REPOSITORY_ATTRIBUTE)(operations)
    return implementation


def move(cell: int = 4) -> MoveRecord:
    return MoveRecord(None, "game-1", cell, MOMENT)


def test_the_implementation_is_a_component_of_the_interface_next_to_it() -> None:
    implementation = getattr(MoveRecords, REPOSITORY_ATTRIBUTE)

    assert vars(sample_entities)[implementation.__name__] is implementation
    assert MoveRecords in implementation.__mro__


def test_a_derived_method_asks_the_operations_with_its_arguments_in_the_order_of_the_name() -> None:
    operations = RecordingOperations()

    implementation_of(GameRecords, operations).find_by_status_and_join_deadline_less_than_equal("waiting", MOMENT)

    [(kind, call)] = operations.calls
    assert (kind, call.query.action, call.arguments) == ("find", Action.FIND, ("waiting", MOMENT))


def test_arguments_may_be_named() -> None:
    operations = RecordingOperations()

    implementation_of(MoveRecords, operations).find_by_game_id_order_by_id_asc(
        game_id="game-1", page=PageRequest.of(2, 10)
    )

    [(_, call)] = operations.calls
    assert (call.arguments, call.page) == (("game-1",), PageRequest(offset=20, limit=10))


def test_lock_locks_the_rows_the_method_reads() -> None:
    operations = RecordingOperations()

    implementation_of(MoveRecords, operations).find_by_played_at_less_than_equal(MOMENT)

    assert operations.calls[0][1].lock is LockMode.PESSIMISTIC_WRITE


def test_count_exists_and_delete_return_what_the_operations_answer() -> None:
    moves = implementation_of(MoveRecords, RecordingOperations())

    assert (moves.count_by_game_id("g"), moves.exists_by_game_id("g"), moves.delete_by_game_id("g")) == (7, True, 2)


def test_an_optional_result_is_the_one_found_or_none() -> None:
    assert implementation_of(MoveRecords, RecordingOperations()).find_first_by_game_id_order_by_id_desc("g") is None
    found = move()
    assert (
        implementation_of(MoveRecords, RecordingOperations([found])).find_first_by_game_id_order_by_id_desc("g")
        is found
    )


def test_a_required_result_that_is_missing_stops_the_call() -> None:
    with pytest.raises(EmptyResultError):
        implementation_of(MoveRecords, RecordingOperations()).find_first_by_order_by_id_asc()


def test_one_result_where_several_were_found_stops_the_call() -> None:
    with pytest.raises(IncorrectResultSizeError, match="found 2"):
        implementation_of(MoveRecords, RecordingOperations([move(), move()])).find_first_by_order_by_id_asc()


def test_save_fills_the_created_date_once_and_the_last_modified_date_every_time() -> None:
    moves = implementation_of(MoveRecords, RecordingOperations())

    saved = moves.save(move())
    created = saved.recorded_at
    saved_again = moves.save(saved)

    assert created is not None
    assert saved_again.recorded_at == created
    assert saved_again.changed_at is not None


def test_crud_methods_select_by_the_identifier() -> None:
    operations = RecordingOperations()
    game_id = uuid4()

    implementation_of(GameRecords, operations).find_by_id(game_id)

    [(_, call)] = operations.calls
    assert ([c.field for c in call.query.alternatives[0]], call.arguments) == (["game_id"], (game_id,))


def test_a_query_runs_its_sql_with_named_arguments_and_makes_its_rows_results() -> None:
    operations = RecordingOperations([CellCount(4, 2)])

    counts = implementation_of(MoveRecords, operations).cell_counts()

    [(_, (native, arguments))] = operations.calls
    assert counts == [CellCount(4, 2)]
    assert (native.result_type, arguments) == (CellCount, {})


def test_a_modifying_query_returns_how_many_rows_it_changed() -> None:
    operations = RecordingOperations()

    changed = implementation_of(MoveRecords, operations).move_every_one_to("game-1", cell=8)

    assert changed == 3
    assert operations.calls[0][1][1] == {"game_id": "game-1", "cell": 8}


def test_a_name_snakeboot_cannot_read_stops_the_start() -> None:
    with pytest.raises(InvalidRepositoryError, match="starts with find_by"):

        class Unreadable(CrudRepository[GameRecord, UUID], Protocol):
            def games_waiting(self) -> list[GameRecord]: ...


def test_too_few_parameters_for_the_conditions_stop_the_start() -> None:
    with pytest.raises(InvalidRepositoryError, match="takes 1 arguments for its conditions, but its name asks for 2"):

        class Short(CrudRepository[GameRecord, UUID], Protocol):
            def find_by_status_and_join_deadline_before(self, status: str) -> list[GameRecord]: ...


def test_a_find_method_that_returns_another_type_stops_the_start() -> None:
    with pytest.raises(InvalidRepositoryError, match="returns GameRecords"):

        class Mismatched(CrudRepository[GameRecord, UUID], Protocol):
            def find_by_status(self, status: str) -> list[MoveRecord]: ...


def test_a_count_method_that_returns_no_int_stops_the_start() -> None:
    with pytest.raises(InvalidRepositoryError, match="returns int"):

        class Miscounted(CrudRepository[GameRecord, UUID], Protocol):
            def count_by_status(self, status: str) -> bool: ...


def test_an_interface_that_names_no_entity_stops_the_start() -> None:
    with pytest.raises(InvalidRepositoryError, match="names no entity"):

        class Nameless(CrudRepository, Protocol):  # type: ignore[type-arg]
            pass
