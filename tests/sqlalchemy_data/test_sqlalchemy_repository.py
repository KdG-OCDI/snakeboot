"""On SQLAlchemy, a repository saves, finds, counts and deletes entities in the session of the running transaction."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

from snakeboot.data import REPOSITORY_ATTRIBUTE, PageRequest
from snakeboot.sqlalchemy_data import Database
from snakeboot.sqlalchemy_data.entity_mapping import EntityMapping
from snakeboot.sqlalchemy_data.sqlalchemy_repository_operations import SqlAlchemyRepositoryOperations
from snakeboot.sqlalchemy_data.testing import in_memory_database
from tests.data.sample_entities import (
    CellCount,
    GameRecord,
    GameRecords,
    MoveRecord,
    MoveRecords,
    PlayedMoveRecord,
    PlayedMoveRecords,
)
from tests.sqlalchemy_data.test_database import RefusedError, fail_in

MOMENT = datetime(2026, 11, 8, 12, tzinfo=UTC)


@pytest.fixture
def database() -> Iterator[Database]:
    database = in_memory_database()
    mapping = EntityMapping.of([MoveRecord, GameRecord, PlayedMoveRecord])
    mapping.metadata.create_all(database.engine, tables=mapping.tables)
    yield database
    database.close()


def repository[R](interface: Callable[..., R], database: Database) -> R:
    operations = SqlAlchemyRepositoryOperations(database, EntityMapping.of([MoveRecord, GameRecord, PlayedMoveRecord]))
    implementation: R = getattr(interface, REPOSITORY_ATTRIBUTE)(operations)
    return implementation


@pytest.fixture
def moves(database: Database) -> MoveRecords:
    return repository(MoveRecords, database)


@pytest.fixture
def games(database: Database) -> GameRecords:
    return repository(GameRecords, database)


def played(moves: MoveRecords, game_id: str, *cells: int) -> list[MoveRecord]:
    return [moves.save(MoveRecord(None, game_id, cell, MOMENT + timedelta(seconds=i))) for i, cell in enumerate(cells)]


def test_save_returns_the_entity_with_the_number_the_database_gave_it(moves: MoveRecords) -> None:
    saved = moves.save(MoveRecord(None, "game-1", 4, MOMENT))

    assert saved.id is not None
    assert saved.recorded_at is not None


def test_save_with_a_known_identifier_updates_the_row(games: GameRecords) -> None:
    game_id = uuid4()
    games.save(GameRecord(game_id, "waiting", ["", "X"], None))

    games.save(GameRecord(game_id, "won", ["O", "X"], None))

    assert games.count() == 1
    found = games.find_by_id(game_id)
    assert found is not None
    assert (found.status, found.board) == ("won", ["O", "X"])


def test_a_change_inside_a_list_is_saved(games: GameRecords, database: Database) -> None:
    game_id = uuid4()
    games.save(GameRecord(game_id, "playing", ["", ""], None))

    with database.transaction():
        game = games.find_by_id(game_id)
        assert game is not None
        game.board[1] = "X"
        games.save(game)

    found = games.find_by_id(game_id)
    assert found is not None
    assert found.board == ["", "X"]


@pytest.mark.parametrize("move", [4, "roll", 2.5, True, {"cell": 4}, [1, 2], None])
def test_any_json_value_reads_back_as_it_was(database: Database, move: object) -> None:
    moves = repository(PlayedMoveRecords, database)

    saved = moves.save(PlayedMoveRecord(None, move, best_move=move, features={"utility": 0.5}, note="seen"))

    assert saved.id is not None
    found = moves.find_by_id(saved.id)
    assert found is not None
    assert (found.move, found.best_move, found.features, found.note) == (move, move, {"utility": 0.5}, "seen")


def test_an_empty_nullable_json_field_is_sql_s_null(database: Database) -> None:
    moves = repository(PlayedMoveRecords, database)

    moves.save(PlayedMoveRecord(None, 4, best_move=None, features=[0.5]))

    with database.session() as session:
        assert session.execute(text("SELECT best_move IS NULL, note IS NULL FROM data_played_move")).one() == (1, 1)


def test_a_date_reads_back_in_utc(games: GameRecords) -> None:
    game_id = uuid4()
    games.save(GameRecord(game_id, "waiting", [], MOMENT.astimezone(timezone(timedelta(hours=2)))))

    found = games.find_by_id(game_id)

    assert found is not None
    assert found.join_deadline == MOMENT
    assert found.join_deadline.tzinfo is UTC


def test_find_by_compares_and_orders_as_the_name_says(moves: MoveRecords) -> None:
    played(moves, "game-1", 4, 0, 8)
    played(moves, "game-2", 2)

    assert [move.cell for move in moves.find_by_game_id_order_by_played_at_asc_id_asc("game-1")] == [4, 0, 8]


def test_conditions_with_a_comparison(games: GameRecords) -> None:
    expired, waiting = uuid4(), uuid4()
    games.save(GameRecord(expired, "waiting", [], MOMENT - timedelta(minutes=1)))
    games.save(GameRecord(waiting, "waiting", [], MOMENT + timedelta(minutes=1)))
    games.save(GameRecord(uuid4(), "playing", [], MOMENT - timedelta(minutes=1)))

    found = games.find_by_status_and_join_deadline_less_than_equal("waiting", MOMENT)

    assert [game.game_id for game in found] == [expired]


def test_in_compares_with_every_value_of_a_list(moves: MoveRecords) -> None:
    played(moves, "game-1", 4, 0, 8)

    assert sorted(move.cell for move in moves.find_by_cell_in([0, 8])) == [0, 8]


def test_a_page_skips_and_limits(moves: MoveRecords) -> None:
    played(moves, "game-1", 1, 2, 3, 4, 5)

    page = moves.find_by_game_id_order_by_id_asc("game-1", PageRequest.of(1, 2))

    assert [move.cell for move in page] == [3, 4]


def test_first_returns_the_one_at_the_top_of_the_order(moves: MoveRecords) -> None:
    played(moves, "game-1", 1, 2, 3)

    last = moves.find_first_by_game_id_order_by_id_desc("game-1")

    assert last is not None
    assert last.cell == 3


def test_a_locking_query_runs(moves: MoveRecords, database: Database) -> None:
    played(moves, "game-1", 1)

    with database.transaction():
        assert len(moves.find_by_played_at_less_than_equal(MOMENT)) == 1


def test_count_exists_and_delete_by_a_condition(moves: MoveRecords) -> None:
    played(moves, "game-1", 1, 2)
    played(moves, "game-2", 3)

    assert (moves.count_by_game_id("game-1"), moves.exists_by_game_id("game-3")) == (2, False)
    assert moves.delete_by_game_id("game-1") == 2
    assert moves.count() == 1


def test_the_crud_methods(games: GameRecords) -> None:
    first = games.save(GameRecord(uuid4(), "waiting", [], None))
    games.save_all([GameRecord(uuid4(), "won", [], None), GameRecord(uuid4(), "lost", [], None)])

    assert (games.count(), games.exists_by_id(first.game_id)) == (3, True)
    games.delete(first)
    games.delete_by_id(uuid4())
    assert sorted(game.status for game in games.find_all()) == ["lost", "won"]
    games.delete_all()
    assert games.count() == 0


def test_a_query_makes_objects_entities_and_scalars_of_its_rows(moves: MoveRecords) -> None:
    played(moves, "game-1", 4, 4, 0)
    played(moves, "game-2", 0)

    assert moves.cell_counts() == [CellCount(0, 2), CellCount(4, 2)]
    assert [move.game_id for move in moves.at_cell(0)] == ["game-1", "game-2"]
    assert moves.games() == 2


def test_a_query_compares_a_date_as_the_column_holds_it(moves: MoveRecords) -> None:
    played(moves, "game-1", 4, 0, 8)  # one second apart from MOMENT on

    until = moves.played_until(MOMENT.astimezone(timezone(timedelta(hours=2))) + timedelta(seconds=1))

    assert [move.cell for move in until] == [4, 0]


def test_a_modifying_query_changes_rows(moves: MoveRecords) -> None:
    played(moves, "game-1", 4, 0)

    assert moves.move_every_one_to("game-1", cell=8) == 2
    assert {move.cell for move in moves.find_all()} == {8}


def test_every_call_of_one_transaction_shares_its_session(moves: MoveRecords, database: Database) -> None:
    counted: list[int] = []

    def play_and_count() -> None:
        played(moves, "game-1", 4)
        counted.append(moves.count())

    with pytest.raises(RefusedError):
        fail_in(database.transaction(), play_and_count)

    assert (counted, moves.count()) == ([1], 0)
