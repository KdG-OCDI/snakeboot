"""`[server] max_upload_size` is optional: an application.toml without it needs no change."""

import pytest
from pydantic import ValidationError

from snakeboot.configuration import ServerProperties, load_configuration
from tests.configuration.sample_service.greeting_properties import GreetingProperties

SAMPLE = "tests.configuration.sample_service"


def server_properties() -> ServerProperties:
    return load_configuration(ServerProperties, GreetingProperties, package=SAMPLE).get(ServerProperties)


def test_without_max_upload_size_it_reads_as_none() -> None:
    assert server_properties().max_upload_size is None


@pytest.mark.parametrize(("value", "size"), [("1048576", 1_048_576), ("20MB", 20_000_000), ("20MiB", 20 * 1024 * 1024)])
def test_max_upload_size_is_a_number_of_bytes_or_a_size_with_its_unit(
    monkeypatch: pytest.MonkeyPatch, value: str, size: int
) -> None:
    monkeypatch.setenv("SERVER__MAX_UPLOAD_SIZE", value)

    assert server_properties().max_upload_size == size


def test_a_max_upload_size_that_is_no_size_stops_the_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVER__MAX_UPLOAD_SIZE", "twenty megabytes")

    with pytest.raises(ValidationError, match="max_upload_size"):
        server_properties()
