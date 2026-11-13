"""The documents of the archive, numbered by the database."""

from dataclasses import dataclass
from typing import Annotated, Protocol

from snakeboot.data import Column, CrudRepository, Id, entity


@entity("archive_document")
@dataclass
class DocumentRecord:
    document_id: Annotated[int | None, Id(generated=True)]
    title: Annotated[str, Column(length=200)]
    clerk: Annotated[str, Column(length=100)]


class DocumentRecords(CrudRepository[DocumentRecord, int], Protocol):
    """The documents."""
