"""What an application's own code imports from snakeboot loads no web framework and no ORM.

The import contracts check snakeboot's own imports; this checks what Python actually loads, the libraries snakeboot
builds on included. A controller, an advice, a command or a use case is then a module that imports without Django,
and stays unchanged when snakeboot binds another framework.
"""

import os
import subprocess
import sys

import pytest

FRAMEWORKS = ("django", "ninja")

PACKAGES_OF_AN_APPLICATION = (
    "snakeboot.rest",
    "snakeboot.command_line",
    "snakeboot.transaction",
    "snakeboot.events",
    "snakeboot.lifecycle",
    "snakeboot.scheduling",
    "snakeboot.component_scan",
    "snakeboot.openapi",
    "snakeboot.configuration",
    "snakeboot.oauth2",
    "snakeboot.rabbitmq",
)


@pytest.mark.parametrize("package", PACKAGES_OF_AN_APPLICATION)
def test_importing_it_loads_no_web_framework(package: str) -> None:
    loaded_frameworks = f"sorted({{m.split('.')[0] for m in sys.modules}} & set({FRAMEWORKS!r}))"
    probe = f"import sys, {package}; print(','.join({loaded_frameworks}))"
    environment = {name: value for name, value in os.environ.items() if name != "DJANGO_SETTINGS_MODULE"}

    loaded = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True, env=environment
    ).stdout.strip()

    assert loaded == ""
