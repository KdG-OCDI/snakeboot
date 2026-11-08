from typing import Literal

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
    """

    host: str
    port: int
    workers: int
    debug: bool
    allowed_hosts: tuple[str, ...]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
