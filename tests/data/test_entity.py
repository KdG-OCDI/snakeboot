"""An entity is a plain dataclass that a table keeps; what cannot be one stops the start."""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated
from uuid import UUID

import pytest

from snakeboot.data import Column, Id, Index, InvalidEntityError, LastModifiedDate, description_of, entity
from tests.data.sample_entities import GameRecord, MoveRecord, PlayedMoveRecord


def test_describes_the_table_and_each_field_in_order() -> None:
    description = description_of(GameRecord)

    assert description.table == "data_game"
    assert [prop.name for prop in description.properties] == ["game_id", "status", "board", "join_deadline"]


def test_the_identifier_is_the_field_marked_with_id() -> None:
    assert description_of(GameRecord).identifier.python_type is UUID


def test_a_field_that_may_be_none_is_nullable_and_keeps_its_type() -> None:
    deadline = description_of(GameRecord).property_named("join_deadline")

    assert deadline is not None
    assert (deadline.python_type, deadline.nullable) == (datetime, True)


def test_a_union_with_none_is_nullable_whatever_else_it_holds() -> None:
    note = description_of(PlayedMoveRecord).property_named("note")

    assert note is not None
    assert (note.python_type, note.nullable) == (int | str, True)


def test_the_markers_of_a_field_are_kept() -> None:
    status = description_of(GameRecord).property_named("status")

    assert status is not None
    assert status.marker(Column) == Column(length=16)


def test_the_indexes_are_kept() -> None:
    assert description_of(MoveRecord).indexes == (Index("data_move_game_idx", "game_id", "played_at"),)


def test_a_class_that_is_no_dataclass_stops_the_start() -> None:
    with pytest.raises(InvalidEntityError, match="marks a dataclass"):

        @entity("loose")
        class Loose:
            id: Annotated[int, Id()]


def test_a_frozen_dataclass_stops_the_start() -> None:
    with pytest.raises(InvalidEntityError, match="frozen or has slots"):

        @entity("frozen")
        @dataclass(frozen=True)
        class Frozen:
            id: Annotated[int, Id()]


def test_an_entity_without_an_identifier_stops_the_start() -> None:
    with pytest.raises(InvalidEntityError, match="marks 0 fields with Id"):

        @entity("anonymous")
        @dataclass
        class Anonymous:
            name: str


def test_an_index_on_a_field_the_entity_lacks_stops_the_start() -> None:
    with pytest.raises(InvalidEntityError, match="names unknown fields"):

        @entity("indexed", indexes=(Index("indexed_colour_idx", "colour"),))
        @dataclass
        class Indexed:
            id: Annotated[int, Id()]
            changed_at: Annotated[datetime | None, LastModifiedDate()] = None


def test_a_class_without_entity_is_none() -> None:
    with pytest.raises(InvalidEntityError, match="is not an @entity"):
        description_of(Column)
