from pydantic import BaseModel

from snakeboot.stereotype import component
from snakeboot.transaction import transactional
from tests.pytest_testing.archive.documents.documents import DocumentRecord, DocumentRecords


class DocumentDTO(BaseModel):
    document_id: int
    title: str
    clerk: str


@component
class FileDocument:
    """The use case: a clerk files a document, which the database numbers."""

    def __init__(self, documents: DocumentRecords) -> None:
        self._documents = documents

    @transactional
    def execute(self, title: str, clerk: str) -> DocumentDTO:
        """Files the document `title` for `clerk`."""
        filed = self._documents.save(DocumentRecord(None, title, clerk))
        return DocumentDTO.model_validate(filed, from_attributes=True)
