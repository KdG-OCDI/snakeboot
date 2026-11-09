"""Entities and repositories as an application declares them, for the tests of snakeboot.data."""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Protocol
from uuid import UUID

from snakeboot.data import (
    Column,
    CreatedBy,
    CreatedDate,
    CrudRepository,
    Id,
    Index,
    Json,
    LastModifiedBy,
    LastModifiedDate,
    LockMode,
    PageRequest,
    Version,
    entity,
    lock,
    query,
)


@entity("data_move", indexes=(Index("data_move_game_idx", "game_id", "played_at"),))
@dataclass
class MoveRecord:
    id: Annotated[int | None, Id(generated=True)]
    game_id: Annotated[str, Column(length=100)]
    cell: int
    played_at: datetime
    recorded_at: Annotated[datetime | None, CreatedDate()] = None
    changed_at: Annotated[datetime | None, LastModifiedDate()] = None


@dataclass
class CellCount:
    cell: int
    times: int


class MoveRecords(CrudRepository[MoveRecord, int], Protocol):
    def find_by_game_id_order_by_played_at_asc_id_asc(self, game_id: str) -> list[MoveRecord]: ...

    def find_by_game_id_order_by_id_asc(self, game_id: str, page: PageRequest) -> list[MoveRecord]: ...

    def find_first_by_game_id_order_by_id_desc(self, game_id: str) -> MoveRecord | None: ...

    def find_first_by_order_by_id_asc(self) -> MoveRecord: ...

    @lock(LockMode.PESSIMISTIC_WRITE)
    def find_by_played_at_less_than_equal(self, moment: datetime) -> list[MoveRecord]: ...

    def find_by_cell_in(self, cells: list[int]) -> list[MoveRecord]: ...

    def count_by_game_id(self, game_id: str) -> int: ...

    def exists_by_game_id(self, game_id: str) -> bool: ...

    def delete_by_game_id(self, game_id: str) -> int: ...

    @query("SELECT cell, COUNT(*) AS times FROM data_move GROUP BY cell ORDER BY cell")
    def cell_counts(self) -> list[CellCount]: ...

    @query("SELECT * FROM data_move WHERE cell = :cell ORDER BY id")
    def at_cell(self, cell: int) -> list[MoveRecord]: ...

    @query("SELECT COUNT(DISTINCT game_id) FROM data_move")
    def games(self) -> int: ...

    @query("SELECT * FROM data_move WHERE played_at <= :moment ORDER BY id")
    def played_until(self, moment: datetime) -> list[MoveRecord]: ...

    @query("UPDATE data_move SET cell = :cell WHERE game_id = :game_id", modifying=True)
    def move_every_one_to(self, game_id: str, cell: int) -> int: ...


@entity("data_played_move")
@dataclass
class PlayedMoveRecord:
    """Any JSON value, as gamelog keeps moves of every game: 4, "roll", {"cell": 4}."""

    id: Annotated[int | None, Id(generated=True)]
    move: Any
    best_move: Any | None
    features: Annotated[dict[str, float] | list[float], Json()]
    note: Annotated[int | str | None, Json()] = None


class PlayedMoveRecords(CrudRepository[PlayedMoveRecord, int], Protocol):
    pass


@entity("data_game")
@dataclass
class GameRecord:
    game_id: Annotated[UUID, Id()]
    status: Annotated[str, Column(length=16)]
    board: list[str]
    join_deadline: datetime | None


class GameRecords(CrudRepository[GameRecord, UUID], Protocol):
    def find_by_status_and_join_deadline_less_than_equal(self, status: str, deadline: datetime) -> list[GameRecord]: ...


@entity("data_workshop")
@dataclass
class WorkshopRecord:
    """An entity that guards against lost updates and records who saved it."""

    id: Annotated[str, Id()]
    title: str
    created_by: Annotated[str | None, CreatedBy()] = None
    modified_by: Annotated[str | None, LastModifiedBy()] = None
    version: Annotated[int | None, Version()] = None


class WorkshopRecords(CrudRepository[WorkshopRecord, str], Protocol):
    @lock(LockMode.PESSIMISTIC_WRITE_SKIP_LOCKED)
    def find_by_title(self, title: str) -> list[WorkshopRecord]: ...
