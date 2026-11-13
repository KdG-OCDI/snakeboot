from typing import Any, Final

from starlette.responses import Response

from snakeboot.rest import DeclaredEndpoint, FileDownload

ANY_MEDIA_TYPE: Final = "*/*"
"""What the OpenAPI document names for a file whose route says nothing of its media type: it is known per call."""

NO_SNIFFING: Final = {"X-Content-Type-Options": "nosniff"}
"""The browser keeps to the `Content-Type` of a file: a file a user uploaded as `text/plain` never runs as a page."""


def file_download_response(download: FileDownload, status: int) -> Response:
    """Returns the answer that holds the file: its bytes, its `Content-Type` and its `Content-Disposition`.

    The `Content-Type` is the media type exactly as the endpoint gave it: Starlette adds no charset to it.
    """
    headers = {
        "Content-Type": download.media_type,
        "Content-Disposition": download.content_disposition,
        **NO_SNIFFING,
    }
    return Response(download.content, status_code=status, headers=headers)


def file_download_documentation(endpoint: DeclaredEndpoint) -> dict[int, Any]:
    """Returns how the OpenAPI document shows the answer of `endpoint`: binary, of the media type it `produces`."""
    media_type = endpoint.route_mapping.produces or ANY_MEDIA_TYPE
    binary = {"schema": {"type": "string", "format": "binary"}}
    return {endpoint.route_mapping.status: {"description": "The file", "content": {media_type: binary}}}
