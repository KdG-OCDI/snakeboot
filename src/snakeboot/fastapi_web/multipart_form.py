import inspect
from typing import Any

from fastapi import File, Form, UploadFile

from snakeboot.rest import UNNAMED_CONTENT_TYPE, DeclaredEndpoint, UploadedFile, UploadTooLargeError


def form_parameters_of(endpoint: DeclaredEndpoint) -> list[inspect.Parameter]:
    """Returns the parameters of `endpoint` as FastAPI reads them, from a form when it takes an `UploadedFile`.

    An endpoint without one keeps its parameters: path, query and body. One with an upload reads a `multipart/form-data`
    form, like Spring's `@RequestParam` in a multipart request: each `UploadedFile` is a file part, read by FastAPI as
    its `UploadFile`, and every other parameter outside the path is a field of the same form. The OpenAPI document
    then shows the form, with a file picker in Swagger UI.
    """
    signature = endpoint.signature
    if not signature.upload_parameters:
        return list(signature.parameters)
    in_path = endpoint.path_parameters
    return [
        parameter if parameter.name in in_path else _form_part(parameter, signature.upload_parameters)
        for parameter in signature.parameters
    ]


def uploaded_file_of(parameter: str, upload: UploadFile, max_size: int) -> UploadedFile:
    """Reads the file FastAPI received for `parameter` into an `UploadedFile`, or raises `UploadTooLargeError`.

    Starlette keeps the part in a temporary file, on disk once it is large; at most `max_size` bytes and one more are
    read from it, so a file that is too large never fills the memory.
    """
    content = upload.file.read(max_size + 1)
    if len(content) > max_size:
        raise UploadTooLargeError(parameter, upload.size if upload.size is not None else len(content), max_size)
    return UploadedFile(upload.filename or "", upload.content_type or UNNAMED_CONTENT_TYPE, content)


def _form_part(parameter: inspect.Parameter, files: tuple[str, ...]) -> inspect.Parameter:
    if parameter.name in files:
        return parameter.replace(annotation=UploadFile, default=File())
    default: Any = Form() if parameter.default is inspect.Parameter.empty else Form(parameter.default)
    return parameter.replace(default=default)
