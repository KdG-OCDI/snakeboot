from collections.abc import Sequence
from importlib import import_module
from typing import ClassVar

from django.core.exceptions import ImproperlyConfigured

from snakeboot.component_scan import ComponentScan


class DjangoConfigurer:
    """Adds Django apps and middleware to the application, like a `WebMvcConfigurer` in Spring.

    Extend it in the component scan or in the package of the application class: snakeboot finds the subclass by
    reading the source, imports its module while it builds Django's settings, and reads two class attributes.

        class CorsConfigurer(DjangoConfigurer):
            installed_apps = ("corsheaders",)
            middleware = ("corsheaders.middleware.CorsMiddleware",)

    `installed_apps` come after the AppConfigs of the scan; `middleware` comes after wireup's and before Django's
    CommonMiddleware, in the order written. The module is imported before Django has started: it holds strings, and
    imports nothing that needs Django's settings, such as Django Ninja or a model.
    """

    installed_apps: ClassVar[tuple[str, ...]] = ()
    middleware: ClassVar[tuple[str, ...]] = ()


def configurers_in(scans: Sequence[ComponentScan]) -> list[type[DjangoConfigurer]]:
    """Returns every `DjangoConfigurer` the scans declare, in the order of their dotted paths."""
    paths = sorted({path for scan in scans for path in scan.classes_extending(DjangoConfigurer.__name__)})
    return [_configurer_at(path) for path in paths]


def _configurer_at(path: str) -> type[DjangoConfigurer]:
    module_name, _, class_name = path.rpartition(".")
    configurer = getattr(import_module(module_name), class_name, None)
    if not (isinstance(configurer, type) and issubclass(configurer, DjangoConfigurer)):
        raise ImproperlyConfigured(f"{path} is written as a DjangoConfigurer, but it is not one when imported.")
    return configurer
