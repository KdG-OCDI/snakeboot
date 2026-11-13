from pydantic import BaseModel

from snakeboot.rest import rest_controller, roles_allowed, route
from snakeboot.security import Principal
from tests.pytest_testing.archive.documents.file_document import DocumentDTO, FileDocument
from tests.pytest_testing.archive.documents.read_document import ReadDocument


class NewDocumentDTO(BaseModel):
    title: str


@rest_controller("/documents")
class DocumentRestController:
    def __init__(self, file_document: FileDocument, read_document: ReadDocument) -> None:
        self._file_document = file_document
        self._read_document = read_document

    @route.post("", status=201)
    @roles_allowed("clerk")
    def file(self, body: NewDocumentDTO, clerk: Principal) -> DocumentDTO:
        return self._file_document.execute(body.title, clerk.name)

    @route.get("/{document_id}")
    @roles_allowed("clerk")
    def read(self, document_id: int) -> DocumentDTO:
        return self._read_document.execute(document_id)
