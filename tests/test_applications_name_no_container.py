"""The sample applications of these tests import snakeboot, and never the container underneath.

An application declares its components with `snakeboot.stereotype` (`@service`, `@repository`, `@component`, `@bean`),
so wireup is to an application what FastAPI and SQLAlchemy are: snakeboot's to bind. The import contracts check
snakeboot's own packages; this reads the source of every sample application, as an application's own contract would.
"""

import ast
from pathlib import Path

import pytest

TESTS = Path(__file__).parent
UNDERNEATH = frozenset(
    {"wireup", "fastapi", "starlette", "uvicorn", "sqlalchemy", "alembic", "psycopg", "redis", "pika", "jwt"}
)


def sample_application_sources() -> list[Path]:
    """Every module of a sample application: the `sample_*` modules and packages, and the projects of the plugin."""
    samples = [*TESTS.glob("*/sample_*"), *(path for path in (TESTS / "pytest_testing").iterdir() if path.is_dir())]
    files = [file for sample in samples for file in ([sample] if sample.is_file() else sample.rglob("*.py"))]
    return sorted(file for file in files if file.suffix == ".py")


def imported_packages(source: Path) -> set[str]:
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = [node for node in ast.walk(tree) if isinstance(node, ast.Import | ast.ImportFrom)]
    names = [
        alias.name if isinstance(node, ast.Import) else (node.module or "") for node in imports for alias in node.names
    ]
    return {name.partition(".")[0] for name in names}


def test_there_are_sample_applications_to_read() -> None:
    assert len(sample_application_sources()) > 20


@pytest.mark.parametrize("source", sample_application_sources(), ids=lambda path: str(path.relative_to(TESTS)))
def test_a_sample_application_names_no_framework_underneath(source: Path) -> None:
    assert imported_packages(source) & UNDERNEATH == set()
