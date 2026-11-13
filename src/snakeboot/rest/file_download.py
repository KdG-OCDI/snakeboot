import re
import unicodedata
from dataclasses import KW_ONLY, dataclass, field
from typing import Final
from urllib.parse import quote

_MEDIA_TYPE: Final = re.compile(r"[A-Za-z0-9][\w!#$&^.+-]*/[A-Za-z0-9][\w!#$&^.+-]*(?:\s*;[^\r\n]*)?", re.ASCII)
"""`type/subtype`, optionally with parameters (`text/csv; charset=utf-8`), on one line."""

_ATTRIBUTE_CHARACTERS: Final = "!#$&+-.^_`|~"
"""What RFC 8187 leaves as it is in `filename*`, next to letters and digits; it percent-encodes the rest."""

_QUOTABLE: Final = frozenset(chr(code) for code in range(0x20, 0x7F)) - {'"', "\\"}
"""What `filename="..."` holds as it is: printable ASCII, without the quote and the backslash it would escape."""


def is_media_type(text: str) -> bool:
    """Whether `text` is a media type such as `application/pdf`, with parameters or without, on one line."""
    return _MEDIA_TYPE.fullmatch(text) is not None


@dataclass(frozen=True, slots=True)
class FileDownload:
    """What an endpoint returns to answer with a file, like Spring's `ResponseEntity<Resource>`.

    The binding of the web framework answers with `content` as it is, `media_type` as its `Content-Type`, and a
    `Content-Disposition` that names `filename`: `attachment`, so the browser saves the file, or `inline=True`, so it
    shows it (a PDF in a tab).

        WORD: Final = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        @route.get("/{proposal_id}/document", produces=WORD)        # produces: the media type in the OpenAPI document
        def download_proposal(self, proposal_id: str) -> FileDownload:
            proposal = self._proposals.render(proposal_id)
            return FileDownload(proposal.content, WORD, filename=f"{proposal.title}.docx")

    A name with accents, or any name beyond plain ASCII, is written twice, as RFC 6266 advises: in UTF-8 in
    `filename*`, and as near as ASCII gets in `filename` for a client that knows no other (`Café.docx` becomes
    `Cafe.docx`). The whole file is in memory, which suits documents of a few megabytes; a file that has to be
    streamed is beyond it.
    """

    content: bytes = field(repr=False)
    media_type: str
    _: KW_ONLY
    filename: str | None = None
    inline: bool = False

    def __post_init__(self) -> None:
        """Refuses a media type or a file name that no `Content-Type` or `Content-Disposition` can carry."""
        if not is_media_type(self.media_type):
            raise ValueError(f"A FileDownload needs a media type such as 'application/pdf', got {self.media_type!r}.")
        if self.filename == "":
            raise ValueError("The file name of a FileDownload is not empty; leave it out for a file without one.")

    @property
    def content_disposition(self) -> str:
        """The value of `Content-Disposition`: `attachment` or `inline`, with the file name as RFC 6266 writes it.

        `attachment; filename="Proposal.docx"`, or for a name beyond plain ASCII
        `attachment; filename="Begroting cafe.docx"; filename*=UTF-8''Begroting%20caf%C3%A9.docx`.
        """
        disposition = "inline" if self.inline else "attachment"
        if self.filename is None:
            return disposition
        if set(self.filename) <= _QUOTABLE:
            return f'{disposition}; filename="{self.filename}"'
        encoded = quote(self.filename, safe=_ATTRIBUTE_CHARACTERS, encoding="utf-8")
        return f"{disposition}; filename=\"{_ascii_of(self.filename)}\"; filename*=UTF-8''{encoded}"


def _ascii_of(filename: str) -> str:
    # Accents come off their letters (é is e and an accent, the accent goes); what has no ASCII letter becomes _.
    letters = (
        character for character in unicodedata.normalize("NFKD", filename) if not unicodedata.combining(character)
    )
    return "".join(character if character in _QUOTABLE else "_" for character in letters)
