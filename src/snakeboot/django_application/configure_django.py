import sys
from types import ModuleType
from typing import Any, Final

from django.core.exceptions import ImproperlyConfigured
from wireup.integration.django import WireupSettings

from snakeboot.component_scan import ComponentScan
from snakeboot.configuration import (
    CONFIGURATION_KEY,
    CacheProperties,
    Configuration,
    DatabaseProperties,
    DjangoProperties,
    begin_configuration,
)

APPLICATION: Final = "snakeboot.django_application"
"""The Django app that reads the sections of the container when Django starts."""

WIREUP_APPLICATION: Final = "wireup.integration.django"
WIREUP_MIDDLEWARE: Final = "wireup.integration.django.wireup_middleware"


def configure_django(settings_module: str, *, package: str, component_scan: ComponentScan) -> None:
    """Sets Django's settings from application.toml and the container from the component scan.

    Like Spring Boot's auto-configuration: settings.py names what goes into the container and its own Django apps,
    snakeboot does the rest. Call it at the bottom of settings.py, after INSTALLED_APPS and MIDDLEWARE:

        configure_django(__name__, package="myservice", component_scan=COMPONENT_SCAN)

    It sets, on the settings module:

        SECRET_KEY, DEBUG, ALLOWED_HOSTS, LOGGING    from [django]
        DATABASES                                    from [database], when application.toml has that table
        CACHES                                       from [cache], when application.toml has that table
        CONFIGURATION                                the sections read, completed when Django starts
        WIREUP                                       the modules of the component scan

    and puts `snakeboot.django_application` and wireup first in INSTALLED_APPS, and wireup's middleware first in
    MIDDLEWARE. A setting that settings.py sets itself and snakeboot would set too stops the start: a value has one
    place. The sections of the container are read when Django starts, by `snakeboot.django_application`.
    """
    settings = sys.modules[settings_module]
    configuration = begin_configuration(
        DjangoProperties, optional=(DatabaseProperties, CacheProperties), package=package
    )
    values = _settings_from(configuration, component_scan)
    _refuse_settings_set_twice(settings, values)
    values["INSTALLED_APPS"] = _first(APPLICATION, WIREUP_APPLICATION, of=getattr(settings, "INSTALLED_APPS", []))
    values["MIDDLEWARE"] = _first(WIREUP_MIDDLEWARE, of=getattr(settings, "MIDDLEWARE", []))
    for name, value in values.items():
        setattr(settings, name, value)


def _settings_from(configuration: Configuration, component_scan: ComponentScan) -> dict[str, Any]:
    django = configuration.get(DjangoProperties)
    values: dict[str, Any] = {
        "SECRET_KEY": django.secret_key.get_secret_value(),
        "DEBUG": django.debug,
        "ALLOWED_HOSTS": list(django.allowed_hosts),
        "LOGGING": _console_logging(django.log_level),
        CONFIGURATION_KEY: configuration,
        "WIREUP": _container_of(configuration, component_scan),
    }
    if DatabaseProperties in configuration.sections:
        values["DATABASES"] = {"default": configuration.get(DatabaseProperties).as_django_database()}
    if CacheProperties in configuration.sections:
        values["CACHES"] = {"default": configuration.get(CacheProperties).as_django_cache()}
    return values


def _container_of(configuration: Configuration, component_scan: ComponentScan) -> WireupSettings:
    # Django's own sections are declared in snakeboot, outside the scan: their modules join the container too.
    modules = [*component_scan.module_names(), *(section.__module__ for section in configuration.sections)]
    return WireupSettings(injectables=list(dict.fromkeys(modules)), auto_inject_views=False)


def _console_logging(level: str) -> dict[str, Any]:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {"console": {"class": "logging.StreamHandler"}},
        "root": {"handlers": ["console"], "level": level},
    }


def _refuse_settings_set_twice(settings: ModuleType, values: dict[str, Any]) -> None:
    twice = [name for name in values if name in vars(settings)]
    if twice:
        raise ImproperlyConfigured(
            f"{settings.__name__} sets {', '.join(twice)} itself, but configure_django sets them from "
            "application.toml: remove them from settings.py, so every value has one place."
        )


def _first(*names: str, of: list[str]) -> list[str]:
    return [*(name for name in names if name not in of), *of]
