from dataclasses import dataclass
from typing import Final

from snakeboot.rest import FileDownload, UploadedFile, rest_controller, route

PDF: Final = "application/pdf"
WORD: Final = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass(frozen=True)
class ReceivedDocumentDTO:
    folder: str
    title: str
    note: str
    filename: str
    content_type: str
    size: int
    text: str


@rest_controller("/folders/{folder}/documents", tags=["documents"])
class DocumentRestController:
    """Sample controller that keeps nothing: it says what it received, and answers with files it makes up."""

    @route.post("", status=201)
    def upload(self, folder: str, document: UploadedFile, title: str, note: str = "none") -> ReceivedDocumentDTO:
        return ReceivedDocumentDTO(
            folder=folder,
            title=title,
            note=note,
            filename=document.filename,
            content_type=document.content_type,
            size=document.size,
            text=document.content.decode(),
        )

    @route.get("/{name}")
    def download(self, folder: str, name: str) -> FileDownload:
        return FileDownload(f"{folder}/{name}".encode(), WORD, filename=name)

    @route.get("/{name}/preview", produces=PDF)
    def preview(self, folder: str, name: str) -> FileDownload:
        return FileDownload(b"%PDF-1.7", PDF, filename=name, inline=True)
