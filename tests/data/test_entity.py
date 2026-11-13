"""An entity is a plain dataclass that a table keeps; what cannot be one stops the start."""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated
from uuid import UUID

import pytest

from snakeboot.data import (
    BigInt,
    Column,
    CreatedBy,
    ForeignKey,
    Id,
    Index,
    InvalidEntityError,
    LastModifiedDate,
    SmallInt,
    UniqueConstraint,
    Version,
    description_of,
    entity,
)
from tests.data.funding_entities import FundingCallRecord, FundingDeadlineRecord, TemplateRecord
from tests.data.sample_entities import GameRecord, MoveRecord, PlayedMoveRecord, WorkshopRecord


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


def test_an_index_may_be_unique_and_partial() -> None:
    (index,) = description_of(TemplateRecord).indexes

    assert (index.columns, index.unique, index.where) == (("source_url",), True, "origin = 'found_at_source'")
    assert (Index("plain_idx", "a").unique, Index("plain_idx", "a").where) == (False, None)


def test_the_unique_constraints_are_kept() -> None:
    assert description_of(FundingCallRecord).unique_constraints == (
        UniqueConstraint("fc_funding_call_audience_uniq", "audience_kind", "reference"),
    )


def test_an_entity_without_unique_constraints_has_none() -> None:
    assert description_of(MoveRecord).unique_constraints == ()


def test_a_foreign_key_and_the_size_of_an_int_are_markers_of_their_field() -> None:
    funding_call_id = description_of(FundingDeadlineRecord).property_named("funding_call_id")

    assert funding_call_id is not None
    assert funding_call_id.marker(BigInt) == BigInt()
    assert funding_call_id.marker(ForeignKey) == ForeignKey(
        "fc_funding_call.id", on_delete="cascade", name="fc_funding_deadline_call_fk"
    )


@pytest.mark.parametrize("target", ["funding_call", "funding_call.", ".id", "public.funding_call.id"])
def test_a_foreign_key_that_names_no_table_and_column_stops_the_start(target: str) -> None:
    with pytest.raises(InvalidEntityError, match=r"names no column: write `table\.column`"):
        ForeignKey(target)


def test_an_on_delete_that_sql_does_not_know_stops_the_start() -> None:
    with pytest.raises(InvalidEntityError, match=r"on_delete='cascades'; it is one of \['cascade', 'no action'"):
        ForeignKey("funding_call.id", on_delete="cascades")  # type: ignore[arg-type]  # reason: the mistake tested


def test_on_delete_set_null_on_a_field_that_may_not_be_empty_stops_the_start() -> None:
    with pytest.raises(InvalidEntityError, match=r'Orphan\.call_id refers to call\.id with on_delete="set null"'):

        @entity("orphan")
        @dataclass
        class Orphan:
            id: Annotated[int, Id()]
            call_id: Annotated[int, ForeignKey("call.id", on_delete="set null")]


@pytest.mark.parametrize(
    ("annotation", "message"),
    [
        pytest.param(Annotated[str, BigInt()], r"Sized\.amount is a BigInt\(\)", id="no int"),
        pytest.param(Annotated[int, BigInt(), SmallInt()], r"is a BigInt\(\) and a SmallInt\(\)", id="two sizes"),
    ],
)
def test_a_size_on_anything_but_an_int_of_one_size_stops_the_start(annotation: object, message: str) -> None:
    with pytest.raises(InvalidEntityError, match=message):

        @entity("sized")
        @dataclass
        class Sized:
            id: Annotated[int, Id()]
            amount: annotation  # type: ignore[valid-type]  # reason: each annotation tested


def test_a_unique_constraint_on_a_field_the_entity_lacks_stops_the_start() -> None:
    with pytest.raises(InvalidEntityError, match="The unique constraint 'kept_colour_uniq' of Kept names unknown"):

        @entity("kept", unique_constraints=(UniqueConstraint("kept_colour_uniq", "colour"),))
        @dataclass
        class Kept:
            id: Annotated[int, Id()]


def test_a_unique_constraint_without_columns_stops_the_start() -> None:
    with pytest.raises(InvalidEntityError, match="The unique constraint 'empty_uniq' names no column"):
        UniqueConstraint("empty_uniq")


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


def test_the_version_is_the_field_marked_with_version() -> None:
    version = description_of(WorkshopRecord).version

    assert version is not None
    assert (version.name, version.python_type, version.nullable) == ("version", int, True)


def test_an_entity_without_a_version_has_none() -> None:
    assert description_of(MoveRecord).version is None


def test_two_versions_stop_the_start() -> None:
    with pytest.raises(InvalidEntityError, match="marks 2 fields with Version"):

        @entity("twice_versioned")
        @dataclass
        class TwiceVersioned:
            id: Annotated[int, Id()]
            first: Annotated[int | None, Version()] = None
            second: Annotated[int | None, Version()] = None


def test_a_version_that_is_no_number_stops_the_start() -> None:
    with pytest.raises(InvalidEntityError, match=r"Stamped\.stamp is a Version\(\), so it is an `int \| None`"):

        @entity("stamped")
        @dataclass
        class Stamped:
            id: Annotated[int, Id()]
            stamp: Annotated[datetime | None, Version()] = None


def test_an_auditor_that_may_not_be_empty_stops_the_start() -> None:
    with pytest.raises(InvalidEntityError, match=r"Audited\.author is a CreatedBy\(\), so it is a `str \| None`"):

        @entity("audited")
        @dataclass
        class Audited:
            id: Annotated[int, Id()]
            author: Annotated[str, CreatedBy()]
