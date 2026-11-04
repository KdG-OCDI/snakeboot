from importlib import import_module
from types import ModuleType

from django.core.exceptions import ImproperlyConfigured
from wireup.integration.django import WireupSettings

from snakeboot.configuration import CONFIGURATION_KEY, Configuration, Section, sections_declared_in


def complete_configuration(settings: object) -> None:
    """Reads the sections declared in the modules of the container, and checks every table of the configuration.

    The second step of the configuration, when Django starts: the modules are the ones wireup builds the container
    from (`settings.WIREUP`), so a section comes along with the module that declares it. A missing value, an unknown
    table or a broken model stops the start here.
    """
    configuration = getattr(settings, CONFIGURATION_KEY, None)
    container = getattr(settings, "WIREUP", None)
    if not isinstance(configuration, Configuration) or not isinstance(container, WireupSettings):
        raise ImproperlyConfigured(
            "snakeboot.django_application needs the settings CONFIGURATION and WIREUP: call configure_django at the "
            "bottom of settings.py."
        )
    configuration.complete(*_sections_in(container))


def _sections_in(container: WireupSettings) -> list[type[Section]]:
    modules = [_module(name_or_module) for name_or_module in container.injectables or ()]
    return [section for module in modules for section in sections_declared_in(module)]


def _module(name_or_module: str | ModuleType) -> ModuleType:
    return import_module(name_or_module) if isinstance(name_or_module, str) else name_or_module
