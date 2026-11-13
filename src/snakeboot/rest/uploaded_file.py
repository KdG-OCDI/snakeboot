from dataclasses import dataclass, field
from typing import Final

DEFAULT_MAX_UPLOAD_SIZE: Final = 1024 * 1024
"""The most bytes an uploaded file holds when `[server] max_upload_size` says nothing: 1 MiB.

Spring Boot's default for `spring.servlet.multipart.max-file-size`. The endpoint gets the file's bytes in memory, so
there is always a limit; an application that takes larger files raises it.
"""

UNNAMED_CONTENT_TYPE: Final = "application/octet-stream"
"""The content type of an uploaded file whose part names none: bytes of an unknown kind."""


@dataclass(frozen=True, slots=True)
class UploadedFile:
    """A file that a call uploads, like Spring's `MultipartFile`: one part of a `multipart/form-data` request.

    An endpoint takes it as a parameter, which the part of the same name fills; the endpoint's other parameters,
    except those of the path, are the other fields of the same form, like `@RequestParam`:

        @route.post("/{call_id}/application-forms", status=201)
        def upload_application_form(self, call_id: str, document: UploadedFile, title: str) -> ApplicationFormDTO:
            return self._forms.store(call_id, title, document.filename, document.content)

    `filename` is the name the client gave the file, `content_type` the media type it named (`application/octet-stream`
    when it named none), `content` the bytes and `size` their number. A file larger than `[server] max_upload_size`
    (1 MiB without it) never reaches the endpoint: the call raises `UploadTooLargeError`. A test builds one as it
    likes: `UploadedFile("idea.md", "text/markdown", b"# An idea")`.
    """

    filename: str
    content_type: str
    content: bytes = field(repr=False)

    @property
    def size(self) -> int:
        """How many bytes the file holds, like `MultipartFile.getSize()`."""
        return len(self.content)


class UploadTooLargeError(ValueError):
    """Raised when an uploaded file holds more than the server takes, like Spring's `MaxUploadSizeExceededException`.

    The endpoint is not called. An advice answers it like any error, and `error_answer(error)` makes it
    `{"code": "upload_too_large", "detail": ...}`:

        @exception_handler(UploadTooLargeError, status=413)
        def answer_upload_too_large(self, error: Exception) -> dict[str, str]:
            return error_answer(error)

    Without an advice for it (or for a base of it), the web framework answers 413 Content Too Large with that body.
    `parameter` names the endpoint's parameter, `size` is what the file holds and `max_size` what the server takes,
    in bytes.
    """

    def __init__(self, parameter: str, size: int, max_size: int) -> None:
        self.parameter = parameter
        self.size = size
        self.max_size = max_size
        super().__init__(f"The file of `{parameter}` holds {size} bytes, more than the {max_size} the server takes.")
