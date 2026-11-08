from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Protocol
from uuid import UUID

from snakeboot.data import Column, CrudRepository, Id, Index, LastModifiedDate, entity


@entity("sample_game", indexes=(Index("sample_game_status_idx", "status"),))
@dataclass
class GameRecord:
    game_id: Annotated[UUID, Id()]
    status: Annotated[str, Column(length=16)]
    board: list[str]
    updated_at: Annotated[datetime | None, LastModifiedDate()] = None


class GameRecords(CrudRepository[GameRecord, UUID], Protocol):
    """The games of the service."""

    def find_by_status_order_by_updated_at_asc(self, status: str) -> list[GameRecord]: ...

    def count_by_status(self, status: str) -> int: ...
