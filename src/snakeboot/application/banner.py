"""The banner of a starting application, like the one Spring Boot prints above its first log line."""

import sys
from importlib.metadata import version
from typing import Final, TextIO

from snakeboot.configuration import Configuration, LoggingProperties, ServerProperties

BANNER: Final = r"""
   _____ _   _____    __ __ __________  ____  ____  ______
  / ___// | / /   |  / //_// ____/ __ )/ __ \/ __ \/_  __/
  \__ \/  |/ / /| | / ,<  / __/ / __  / / / / / / / / /
 ___/ / /|  / ___ |/ /| |/ /___/ /_/ / /_/ / /_/ / / /
/____/_/ |_/_/  |_/_/ |_/_____/_____/\____/\____/ /_/
"""
"""snakeboot's name, drawn in characters every console shows."""

_WIDTH: Final = max(len(line) for line in BANNER.splitlines())


def banner() -> str:
    """Returns the banner with the version of snakeboot under it, as Spring Boot names its own."""
    name, release = " :: snakeboot ::", f"(v{version('snakeboot')})"
    return f"{BANNER}{name}{release.rjust(_WIDTH - len(name))}\n\n"


def print_banner(configuration: Configuration, stream: TextIO | None = None) -> None:
    """Prints the banner where the log lines go, when a process that keeps running starts: `serve`, `run_lifecycle`.

    `[server] banner = false` leaves it out, like `spring.main.banner-mode=off`. So does `[logging] format = "ecs"`:
    a log store that reads one JSON object per line would stumble over it.
    """
    if configuration.get(ServerProperties).banner is False or _is_structured(configuration):
        return
    (stream or sys.stderr).write(banner())


def _is_structured(configuration: Configuration) -> bool:
    return LoggingProperties in configuration.sections and configuration.get(LoggingProperties).format == "ecs"
