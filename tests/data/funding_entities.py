"""Entities that describe, with its own names, a schema that Django left on PostgreSQL: foreign keys, a unique
constraint, a partial unique index, BIGINT and SMALLINT columns."""

from dataclasses import dataclass
from typing import Annotated, Protocol
from uuid import UUID

from snakeboot.data import (
    BigInt,
    Column,
    CrudRepository,
    ForeignKey,
    Id,
    Index,
    SmallInt,
    UniqueConstraint,
    entity,
)

SCHEMA = """
CREATE TABLE fc_funding_call (
    id BIGINT NOT NULL,
    audience_kind VARCHAR(20) NOT NULL,
    reference VARCHAR(40) NOT NULL,
    budget BIGINT,
    CONSTRAINT fc_funding_call_pkey PRIMARY KEY (id),
    CONSTRAINT fc_funding_call_audience_uniq UNIQUE (audience_kind, reference)
);
CREATE TABLE fc_funding_deadline (
    id BIGINT NOT NULL,
    funding_call_id BIGINT NOT NULL,
    stage SMALLINT NOT NULL,
    CONSTRAINT fc_funding_deadline_pkey PRIMARY KEY (id),
    CONSTRAINT fc_funding_deadline_call_fk FOREIGN KEY (funding_call_id) REFERENCES fc_funding_call (id)
        ON DELETE CASCADE
);
CREATE INDEX fc_funding_deadline_call_idx ON fc_funding_deadline (funding_call_id);
CREATE TABLE fc_call_note (
    id BIGINT NOT NULL,
    funding_call_id BIGINT NOT NULL,
    note TEXT NOT NULL,
    CONSTRAINT fc_call_note_pkey PRIMARY KEY (id),
    CONSTRAINT fc_call_note_funding_call_id_fk FOREIGN KEY (funding_call_id) REFERENCES fc_funding_call (id)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE fc_template (
    id UUID NOT NULL,
    source_url TEXT NOT NULL,
    origin VARCHAR(20) NOT NULL,
    CONSTRAINT fc_template_pkey PRIMARY KEY (id)
);
CREATE UNIQUE INDEX fc_template_source_url_uniq ON fc_template (source_url) WHERE origin = 'found_at_source';
"""
"""The schema as a migration writes it, in SQL that PostgreSQL and SQLite both run."""


@entity(
    "fc_funding_call",
    unique_constraints=(UniqueConstraint("fc_funding_call_audience_uniq", "audience_kind", "reference"),),
)
@dataclass
class FundingCallRecord:
    id: Annotated[int, Id(), BigInt()]
    audience_kind: Annotated[str, Column(length=20)]
    reference: Annotated[str, Column(length=40)]
    budget: Annotated[int | None, BigInt()] = None


@entity("fc_funding_deadline", indexes=(Index("fc_funding_deadline_call_idx", "funding_call_id"),))
@dataclass
class FundingDeadlineRecord:
    id: Annotated[int, Id(), BigInt()]
    funding_call_id: Annotated[
        int, BigInt(), ForeignKey("fc_funding_call.id", on_delete="cascade", name="fc_funding_deadline_call_fk")
    ]
    stage: Annotated[int, SmallInt()]


@entity("fc_call_note")
@dataclass
class CallNoteRecord:
    """Refers to its funding call as Django does: checked at the commit, and in the way of deleting the call."""

    id: Annotated[int, Id(), BigInt()]
    funding_call_id: Annotated[
        int, BigInt(), ForeignKey("fc_funding_call.id", name="fc_call_note_funding_call_id_fk", deferred=True)
    ]
    note: str


@entity(
    "fc_template",
    indexes=(Index("fc_template_source_url_uniq", "source_url", unique=True, where="origin = 'found_at_source'"),),
)
@dataclass
class TemplateRecord:
    id: Annotated[UUID, Id()]
    source_url: str
    origin: Annotated[str, Column(length=20)]


ENTITIES = (FundingCallRecord, FundingDeadlineRecord, CallNoteRecord, TemplateRecord)


class FundingCallRecords(CrudRepository[FundingCallRecord, int], Protocol):
    pass


class FundingDeadlineRecords(CrudRepository[FundingDeadlineRecord, int], Protocol):
    pass


class CallNoteRecords(CrudRepository[CallNoteRecord, int], Protocol):
    pass


class TemplateRecords(CrudRepository[TemplateRecord, UUID], Protocol):
    pass
