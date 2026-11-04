from collections.abc import Sequence
from typing import Final

from django.core.exceptions import ImproperlyConfigured

from snakeboot.component_scan import ComponentScan
from snakeboot.django_application.django_configurer import DjangoConfigurer

APPLICATION: Final = "snakeboot.django_application"
"""The Django app that reads the sections of the container and installs the transaction manager when Django starts."""

WIREUP_APPLICATION: Final = "wireup.integration.django"
WIREUP_MIDDLEWARE: Final = "wireup.integration.django.wireup_middleware"
COMMON_MIDDLEWARE: Final = "django.middleware.common.CommonMiddleware"


def installed_apps(scans: Sequence[ComponentScan], configurers: Sequence[type[DjangoConfigurer]]) -> list[str]:
    """Returns INSTALLED_APPS: snakeboot, wireup, every `AppConfig` of the scans, then what the configurers add.

    The scans read the source and import nothing, so this works before Django has started. An app that a configurer
    adds although a scan finds it, or a model outside every app, stops the start.
    """
    found = list(dict.fromkeys(app for scan in scans for app in scan.app_configs()))
    added = {app: configurer for configurer in configurers for app in configurer.installed_apps}
    _refuse_apps_added_twice(found, added)
    _refuse_models_outside_apps([model for scan in scans for model in scan.models()], found)
    return [APPLICATION, WIREUP_APPLICATION, *found, *added]


def middleware(configurers: Sequence[type[DjangoConfigurer]]) -> list[str]:
    """Returns MIDDLEWARE: wireup's, then what the configurers add in the order they write it, then CommonMiddleware.

    Middleware such as django-cors-headers' must come before CommonMiddleware, and wireup's opens the request scope
    that every other one may use.
    """
    added = dict.fromkeys(entry for configurer in configurers for entry in configurer.middleware)
    return [WIREUP_MIDDLEWARE, *added, COMMON_MIDDLEWARE]


def _refuse_apps_added_twice(found: list[str], added: dict[str, type[DjangoConfigurer]]) -> None:
    found_packages = {_package_of_app(app) for app in found}
    for app, configurer in added.items():
        if app in found or app in found_packages:
            raise ImproperlyConfigured(
                f"{configurer.__name__} adds {app} to INSTALLED_APPS, but the component scan finds it already: "
                "remove it from installed_apps."
            )


def _refuse_models_outside_apps(models: list[str], app_configs: list[str]) -> None:
    packages = {_package_of_app(app_config) for app_config in app_configs}
    for model in models:
        module, _, _ = model.rpartition(".")
        if not any(module == package or module.startswith(f"{package}.") for package in packages):
            raise ImproperlyConfigured(
                f"{model} is a Django model outside every app: give its package an AppConfig in apps.py, so that "
                "Django knows its table and its migrations."
            )


def _package_of_app(app_config: str) -> str:
    # "myapp.persistence.apps.PersistenceConfig": the app is the package that holds apps.py.
    module, _, _ = app_config.rpartition(".")
    package, _, _ = module.rpartition(".")
    return package
