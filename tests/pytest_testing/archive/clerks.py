"""The clerks of the archive, by the key they call the API with."""

from dataclasses import dataclass
from typing import Annotated, Protocol

from snakeboot.data import Column, CrudRepository, Id, entity


@entity("archive_clerk")
@dataclass
class ClerkRecord:
    api_key: Annotated[str, Id(), Column(length=64)]
    name: Annotated[str, Column(length=100)]


class ClerkRecords(CrudRepository[ClerkRecord, str], Protocol):
    """The clerks."""
