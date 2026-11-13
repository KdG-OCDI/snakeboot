"""An uploaded file and a file to download are plain values, in no web framework's terms."""

import pytest

from snakeboot.rest import FileDownload, UploadedFile, UploadTooLargeError, error_answer

PDF = "application/pdf"


def test_an_uploaded_file_counts_its_bytes_and_keeps_them_out_of_its_repr() -> None:
    uploaded = UploadedFile("idea.md", "text/markdown", b"# An idea")

    assert uploaded.size == 9
    assert repr(uploaded) == "UploadedFile(filename='idea.md', content_type='text/markdown')"


def test_a_file_too_large_is_an_error_with_a_stable_code() -> None:
    error = UploadTooLargeError("document", 2_000_000, 1_048_576)

    assert (error.parameter, error.size, error.max_size) == ("document", 2_000_000, 1_048_576)
    assert error_answer(error) == {
        "code": "upload_too_large",
        "detail": "The file of `document` holds 2000000 bytes, more than the 1048576 the server takes.",
    }


@pytest.mark.parametrize(
    ("download", "disposition"),
    [
        (FileDownload(b"", PDF, filename="Proposal 2026.pdf"), 'attachment; filename="Proposal 2026.pdf"'),
        (FileDownload(b"", PDF, filename="Proposal.pdf", inline=True), 'inline; filename="Proposal.pdf"'),
        (FileDownload(b"", PDF), "attachment"),
        (FileDownload(b"", PDF, inline=True), "inline"),
        (
            FileDownload(b"", PDF, filename="Aanvraag Zoë.pdf"),
            "attachment; filename=\"Aanvraag Zoe.pdf\"; filename*=UTF-8''Aanvraag%20Zo%C3%AB.pdf",
        ),
        (
            FileDownload(b"", PDF, filename="Begroting 2026 €.pdf"),
            "attachment; filename=\"Begroting 2026 _.pdf\"; filename*=UTF-8''Begroting%202026%20%E2%82%AC.pdf",
        ),
        (
            FileDownload(b"", PDF, filename='The "best" offer.pdf'),
            "attachment; filename=\"The _best_ offer.pdf\"; filename*=UTF-8''The%20%22best%22%20offer.pdf",
        ),
        (
            FileDownload(b"", PDF, filename="two\r\nlines.pdf"),
            "attachment; filename=\"two__lines.pdf\"; filename*=UTF-8''two%0D%0Alines.pdf",
        ),
    ],
    ids=["ascii", "inline", "without a name", "inline without a name", "accents", "no ascii", "quotes", "line break"],
)
def test_the_content_disposition_names_the_file_as_rfc_6266_writes_it(download: FileDownload, disposition: str) -> None:
    assert download.content_disposition == disposition


def test_a_file_to_download_keeps_its_bytes_out_of_its_repr() -> None:
    assert repr(FileDownload(b"%PDF", PDF, filename="a.pdf")) == (
        "FileDownload(media_type='application/pdf', filename='a.pdf', inline=False)"
    )


@pytest.mark.parametrize("media_type", ["", "pdf", "application/", "text/plain\r\nSet-Cookie: x=1"])
def test_a_file_to_download_needs_a_media_type(media_type: str) -> None:
    with pytest.raises(ValueError, match="needs a media type"):
        FileDownload(b"", media_type)


def test_a_media_type_may_have_parameters() -> None:
    assert FileDownload(b"a;b", "text/csv; charset=utf-8").media_type == "text/csv; charset=utf-8"


def test_a_file_name_is_not_empty() -> None:
    with pytest.raises(ValueError, match="not empty"):
        FileDownload(b"", PDF, filename="")
