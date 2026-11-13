from typing import Any, Literal

from pydantic import ByteSize, model_validator

from snakeboot.configuration.configuration_properties import configuration_properties
from snakeboot.configuration.section import Section


@configuration_properties("server")
class ServerProperties(Section):
    """The section `[server]`: the web server of every application, like Spring Boot's `server.*`.

    `host` and `port` are where `python -m myapp serve` listens, like `server.address` and `server.port`; `workers` is
    how many processes serve it. `debug` turns on the framework's debug answers; `allowed_hosts` are the host names the
    server answers (`*` for any, `*.example.com` for every subdomain); `log_level` is the level of the root logger,
    like `logging.level.root`. Whichever server runs the application reads them here, so the table keeps its name when
    the framework changes.

        [server]
        host = "0.0.0.0"          # every interface, as in a container; "127.0.0.1" for this machine only
        port = 8000
        workers = 1
        debug = false
        allowed_hosts = ["*"]
        log_level = "INFO"
        max_upload_size = "20MB"  # optional: 1 MiB without it

    The optional `max_upload_size` is the most an `UploadedFile` holds, like `spring.servlet.multipart.max-file-size`:
    a number of bytes, or a size with its unit, "20MB" for 20 million bytes or "20MiB" for 20 times 1024 squared. A
    larger file is refused with `UploadTooLargeError` (413). Without the key it reads as None, and the REST API takes
    files of up to 1 MiB, Spring Boot's default.
    """

    host: str
    port: int
    workers: int
    debug: bool
    allowed_hosts: tuple[str, ...]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    max_upload_size: ByteSize | None

    @model_validator(mode="before")
    @classmethod
    def _without_an_upload_limit(cls, table: Any) -> Any:
        # A profile and the environment change keys and cannot write None: a missing key reads as None.
        return {"max_upload_size": None, **table} if isinstance(table, dict) else table
