"""On FastAPI, an endpoint takes an uploaded file from a multipart form, and answers with a file and its headers."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ByteSize

from snakeboot.configuration import CorsProperties, ServerProperties
from snakeboot.fastapi_web import rest_api
from snakeboot.rest import DEFAULT_MAX_UPLOAD_SIZE
from tests.rest.files.document_rest_controller import PDF, WORD
from tests.rest.sample_application import FilesApplication, UnadvisedFilesApplication

MINUTES = {"document": ("Notulen.md", b"# Notulen", "text/markdown")}


def client_of(application: type, *, max_upload_size: int | None = None) -> TestClient:
    """A client of the API, served as `[server]` says, with `max_upload_size` when given and without it else."""
    server = ServerProperties(
        host="127.0.0.1",
        port=8000,
        workers=1,
        debug=False,
        allowed_hosts=("*",),
        log_level="INFO",
        max_upload_size=ByteSize(max_upload_size) if max_upload_size is not None else None,
    )
    return TestClient(rest_api(application, lambda component: component(), server=server))


@pytest.fixture
def client() -> TestClient:
    return client_of(FilesApplication)


def openapi_of(client: TestClient) -> dict[str, Any]:
    document: dict[str, Any] = client.get("/api/openapi.json").json()
    return document


def test_an_endpoint_receives_the_uploaded_file_and_the_other_fields_of_its_form(client: TestClient) -> None:
    response = client.post("/api/folders/minutes/documents", files=MINUTES, data={"title": "Board, 12 November"})

    assert response.status_code == 201
    assert response.json() == {
        "folder": "minutes",
        "title": "Board, 12 November",
        "note": "none",
        "filename": "Notulen.md",
        "content_type": "text/markdown",
        "size": 9,
        "text": "# Notulen",
    }


def test_a_field_of_the_form_with_a_default_takes_the_value_sent(client: TestClient) -> None:
    response = client.post("/api/folders/minutes/documents", files=MINUTES, data={"title": "Board", "note": "draft"})

    assert response.json()["note"] == "draft"


def test_a_file_whose_part_names_no_type_is_octet_stream(client: TestClient) -> None:
    body = (
        b"--boundary\r\n"
        b'Content-Disposition: form-data; name="title"\r\n\r\nRaw\r\n'
        b"--boundary\r\n"
        b'Content-Disposition: form-data; name="document"; filename="data"\r\n\r\n\x00\x01\r\n'
        b"--boundary--\r\n"
    )

    response = client.post(
        "/api/folders/raw/documents",
        content=body,
        headers={"Content-Type": "multipart/form-data; boundary=boundary"},
    )

    assert (response.json()["content_type"], response.json()["size"]) == ("application/octet-stream", 2)


def test_a_call_without_the_file_is_an_invalid_request(client: TestClient) -> None:
    response = client.post("/api/folders/minutes/documents", data={"title": "Board"})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "document"]


def test_a_file_larger_than_max_upload_size_is_answered_by_the_advice() -> None:
    client = client_of(FilesApplication, max_upload_size=8)

    response = client.post("/api/folders/minutes/documents", files=MINUTES, data={"title": "Board"})

    assert response.status_code == 413
    assert response.json() == {
        "code": "upload_too_large",
        "detail": "The file of `document` holds 9 bytes, more than the 8 the server takes.",
        "max_size": 8,
    }


def test_without_an_advice_a_file_too_large_is_answered_413_in_snakeboot_s_words() -> None:
    client = client_of(UnadvisedFilesApplication, max_upload_size=8)

    response = client.post("/api/folders/minutes/documents", files=MINUTES, data={"title": "Board"})

    assert (response.status_code, response.json()["code"]) == (413, "upload_too_large")


def test_without_max_upload_size_a_file_of_one_mebibyte_is_taken_and_one_byte_more_refused(client: TestClient) -> None:
    def upload(size: int) -> int:
        files = {"document": ("large.txt", b"x" * size, "text/plain")}
        return client.post("/api/folders/large/documents", files=files, data={"title": "Large"}).status_code

    assert DEFAULT_MAX_UPLOAD_SIZE == 1024 * 1024
    assert (upload(DEFAULT_MAX_UPLOAD_SIZE), upload(DEFAULT_MAX_UPLOAD_SIZE + 1)) == (201, 413)


def test_the_openapi_document_shows_a_form_with_a_binary_file_for_swagger_ui_s_file_picker(client: TestClient) -> None:
    document = openapi_of(client)
    operation = document["paths"]["/api/folders/{folder}/documents"]["post"]

    assert [parameter["name"] for parameter in operation["parameters"]] == ["folder"]
    form = operation["requestBody"]["content"]["multipart/form-data"]["schema"]["$ref"].rpartition("/")[2]
    schema = document["components"]["schemas"][form]
    assert schema["properties"]["document"] == {
        "type": "string",
        "contentMediaType": "application/octet-stream",
        "title": "Document",
    }
    assert schema["properties"]["title"]["type"] == "string"
    assert schema["required"] == ["document", "title"]


def test_a_download_names_a_file_with_accents_in_ascii_and_in_utf_8(client: TestClient) -> None:
    response = client.get("/api/folders/budgets/documents/Begroting café.docx")

    assert response.status_code == 200
    assert response.headers["Content-Type"] == WORD
    assert response.headers["Content-Disposition"] == (
        "attachment; filename=\"Begroting cafe.docx\"; filename*=UTF-8''Begroting%20caf%C3%A9.docx"
    )
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.content == "budgets/Begroting café.docx".encode()


def test_an_inline_download_is_shown_by_the_browser(client: TestClient) -> None:
    response = client.get("/api/folders/posters/documents/Poster.pdf/preview")

    assert response.headers["Content-Type"] == PDF
    assert response.headers["Content-Disposition"] == 'inline; filename="Poster.pdf"'
    assert response.content == b"%PDF-1.7"


def test_the_script_of_a_page_of_an_allowed_origin_may_read_the_file_name() -> None:
    cors = CorsProperties(
        allowed_origins=("https://app.example",), allowed_methods=("GET",), allowed_headers=(), allow_credentials=False
    )
    client = TestClient(rest_api(FilesApplication, lambda component: component(), cors=cors))

    response = client.get("/api/folders/posters/documents/Poster.pdf", headers={"Origin": "https://app.example"})

    assert response.headers["Access-Control-Expose-Headers"] == "Content-Disposition"


def test_the_openapi_document_shows_a_binary_answer_of_the_media_type_the_route_produces(client: TestClient) -> None:
    paths = openapi_of(client)["paths"]
    binary = {"schema": {"type": "string", "format": "binary"}}

    assert paths["/api/folders/{folder}/documents/{name}/preview"]["get"]["responses"]["200"]["content"] == {
        PDF: binary
    }
    assert paths["/api/folders/{folder}/documents/{name}"]["get"]["responses"]["200"]["content"] == {"*/*": binary}
