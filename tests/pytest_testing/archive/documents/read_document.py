from snakeboot.stereotype import component
from tests.pytest_testing.archive.documents.documents import DocumentRecords
from tests.pytest_testing.archive.documents.file_document import DocumentDTO


class DocumentNotFoundError(LookupError):
    """The archive holds no document of that number."""


@component
class ReadDocument:
    """The use case: a clerk reads a document that was filed."""

    def __init__(self, documents: DocumentRecords) -> None:
        self._documents = documents

    def execute(self, document_id: int) -> DocumentDTO:
        """Returns the document `document_id`."""
        document = self._documents.find_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError(f"The archive holds no document {document_id}.")
        return DocumentDTO.model_validate(document, from_attributes=True)
