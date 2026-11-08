from typing import Literal

from snakeboot.configuration.configuration_properties import configuration_properties
from snakeboot.configuration.section import Section


@configuration_properties("server")
class ServerProperties(Section):
    """The section `[server]`: what the web server of every application needs, like Spring Boot's `server.*`.

    `debug` turns on the framework's debug answers; `allowed_hosts` are the host names the server answers (`*` for
    any, `*.example.com` for every subdomain); `log_level` is the level of the root logger, like
    `logging.level.root`. Whichever framework serves the application reads them here, so the table keeps its name
    when the framework changes.
    """

    debug: bool
    allowed_hosts: tuple[str, ...]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
