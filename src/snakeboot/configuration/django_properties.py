from typing import Literal

from pydantic import SecretStr

from snakeboot.configuration.configuration_properties import configuration_properties
from snakeboot.configuration.section import Section


@configuration_properties("django")
class DjangoProperties(Section):
    """The section `[django]`: what settings.py hands to Django itself, like Spring Boot's `server.*` properties.

    `secret_key` is a SecretStr, so it never shows in a log or a traceback; settings.py unwraps it once.
    """

    secret_key: SecretStr
    debug: bool
    allowed_hosts: tuple[str, ...]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
