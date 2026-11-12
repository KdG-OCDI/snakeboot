"""What an application's own code imports from snakeboot loads no web, persistence or cache framework.

The import contracts check snakeboot's own imports; this checks what Python actually loads, the libraries snakeboot
builds on included. A controller, an entity, a repository, a command or a use case is then a module that imports
without FastAPI or SQLAlchemy, and stays unchanged when snakeboot binds another framework. `snakeboot.boot` loads none
either: a command that needs no server or database starts without them.

wireup itself imports FastAPI when it is installed (its `Inject()` doubles as FastAPI's `Depends`), so the test
counts what snakeboot loads beyond what `import wireup` loaded.
"""

import subprocess
import sys

import pytest

FRAMEWORKS = ("fastapi", "starlette", "uvicorn", "sqlalchemy", "alembic", "psycopg", "redis")

PACKAGES_OF_AN_APPLICATION = (
    "snakeboot.boot",
    "snakeboot.rest",
    "snakeboot.data",
    "snakeboot.cache",
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
    "snakeboot.testing",
    "snakeboot.pytest_testing.pytest_plugin",
)


@pytest.mark.parametrize("package", PACKAGES_OF_AN_APPLICATION)
def test_importing_it_loads_no_framework(package: str) -> None:
    frameworks = f"{{m.split('.')[0] for m in sys.modules}} & set({FRAMEWORKS!r})"
    probe = (
        f"import sys, wireup; before = {frameworks}; import {package}; print(','.join(sorted({frameworks} - before)))"
    )

    loaded = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True).stdout.strip()

    assert loaded == ""
