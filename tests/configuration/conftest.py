import os

import pytest

from snakeboot.configuration import PROFILE_VARIABLE

SECTIONS_OF_THE_SAMPLE = ("DJANGO__", "GREETING__", "FAREWELL__")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts without a profile and without overrides, whatever the machine has set."""
    monkeypatch.delenv(PROFILE_VARIABLE, raising=False)
    for name in list(os.environ):
        if name.upper().startswith(SECTIONS_OF_THE_SAMPLE):
            monkeypatch.delenv(name)
