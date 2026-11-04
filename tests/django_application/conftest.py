import os
import sys
from types import ModuleType

import pytest

from snakeboot.configuration import PROFILE_VARIABLE

SECTIONS_OF_THE_SERVICES = ("DJANGO__", "DATABASE__", "CACHE__", "GREETING__")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts without a profile and without overrides, whatever the machine has set."""
    monkeypatch.delenv(PROFILE_VARIABLE, raising=False)
    for name in list(os.environ):
        if name.upper().startswith(SECTIONS_OF_THE_SERVICES):
            monkeypatch.delenv(name)


@pytest.fixture
def settings_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """A fresh settings.py with the service's own apps and middleware, as configure_django finds it."""
    module = ModuleType("tests.django_application.settings_under_test")
    module.INSTALLED_APPS = ["tests.django_application.service"]  # type: ignore[attr-defined]  # a settings module
    module.MIDDLEWARE = ["django.middleware.common.CommonMiddleware"]  # type: ignore[attr-defined]  # idem
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return module
