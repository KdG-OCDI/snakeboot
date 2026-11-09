from typing import Literal

from snakeboot.configuration.configuration_properties import configuration_properties
from snakeboot.configuration.section import Section


@configuration_properties("logging")
class LoggingProperties(Section):
    """The optional section `[logging]`: how log lines are written, like Spring Boot's `logging.structured.format`.

    Without the section a line is plain text, for a person reading a console. `format = "ecs"` writes every line as
    one JSON object in the Elastic Common Schema, for a log store (Loki, Elasticsearch) that reads fields instead of
    text: the level, the logger, the service, the trace id, the error and its stack trace each have a field of their
    own. The level stays `[server] log_level`.

        [logging]
        format = "ecs"          # or LOGGING__FORMAT=ecs in the environment of the container
    """

    format: Literal["plain", "ecs"]
