"""Runs the import-linter contracts of pyproject.toml as part of the normal test run.

import-linter reconfigures logging and disables every existing logger, so it runs in a
separate process: otherwise tests that run after it could no longer capture log output.
"""

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LINT_IMPORTS = shutil.which("lint-imports", path=str(Path(sys.executable).parent))


def test_import_contracts_are_kept() -> None:
    assert LINT_IMPORTS is not None, "lint-imports is not installed in this environment."
    result = subprocess.run(
        [LINT_IMPORTS, "--no-cache"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert "Contracts:" in result.stdout, result.stdout + result.stderr
    assert result.returncode == 0, result.stdout + result.stderr
