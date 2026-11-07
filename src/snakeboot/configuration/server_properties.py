from typing import Literal

from pydantic import SecretStr

from snakeboot.configuration.configuration_properties import configuration_properties
from snakeboot.configuration.section import Section


@configuration_properties("server")
class ServerProperties(Section):
    """The section `[server]`: what the web server of every application needs, like Spring Boot's `server.*`.

    `secret_key` signs what the server hands out (sessions, CSRF tokens) and is a SecretStr, so it never shows in a
    log or a traceback; `debug` turns on the framework's debug pages; `allowed_hosts` are the host names the server
    answers; `log_level` is the level of the root logger, like `logging.level.root`. Whichever framework serves the
    application reads them here, so the table keeps its name when the framework changes.
    """

    secret_key: SecretStr
    debug: bool
    allowed_hosts: tuple[str, ...]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
