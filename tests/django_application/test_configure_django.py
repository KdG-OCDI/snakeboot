"""`configure_django` sets Django's settings from application.toml and the container from the component scan."""

from importlib import import_module
from types import ModuleType

import pytest
import wireup
from django.core.exceptions import ImproperlyConfigured
from pydantic import ValidationError

from snakeboot.component_scan import ComponentScan
from snakeboot.configuration import CONFIGURATION_KEY, Configuration, DatabaseProperties, DjangoProperties
from snakeboot.django_application import APPLICATION, configure_django
from snakeboot.django_application.configure_django import WIREUP_APPLICATION, WIREUP_MIDDLEWARE
from snakeboot.django_application.container_sections import complete_configuration
from tests.django_application.container.greeting_properties import GreetingProperties

SERVICE = "tests.django_application.service"
SERVICE_WITHOUT_DATABASE = "tests.django_application.service_without_database"
CONTAINER = ComponentScan(base_packages=("tests.django_application.container",))
CONTAINER_WITHOUT_SECTIONS = ComponentScan(base_packages=("tests.django_application.empty_container",))


def configure(settings: ModuleType, package: str = SERVICE, component_scan: ComponentScan = CONTAINER) -> None:
    configure_django(settings.__name__, package=package, component_scan=component_scan)


def configuration_of(settings: ModuleType) -> Configuration:
    configuration = getattr(settings, CONFIGURATION_KEY)
    assert isinstance(configuration, Configuration)
    return configuration


def test_the_django_settings_come_from_the_django_table(settings_module: ModuleType) -> None:
    configure(settings_module)

    assert settings_module.SECRET_KEY == "test-only-secret"
    assert settings_module.DEBUG is False
    assert settings_module.ALLOWED_HOSTS == ["greeting.example"]
    assert settings_module.LOGGING["root"]["level"] == "WARNING"


def test_the_database_table_becomes_databases(settings_module: ModuleType) -> None:
    configure(settings_module)

    assert settings_module.DATABASES["default"]["HOST"] == "db"
    assert not hasattr(settings_module, "CACHES")


def test_without_a_database_table_settings_get_no_databases(settings_module: ModuleType) -> None:
    configure(settings_module, package=SERVICE_WITHOUT_DATABASE)

    assert not hasattr(settings_module, "DATABASES")


def test_settings_may_set_what_application_toml_does_not_hold(settings_module: ModuleType) -> None:
    settings_module.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3"}}  # type: ignore[attr-defined]

    configure(settings_module, package=SERVICE_WITHOUT_DATABASE)

    assert settings_module.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"


def test_a_setting_set_twice_stops_the_start(settings_module: ModuleType) -> None:
    settings_module.DEBUG = True  # type: ignore[attr-defined]  # the point: settings.py sets it too

    with pytest.raises(ImproperlyConfigured, match="sets DEBUG itself"):
        configure(settings_module)


def test_snakeboot_and_wireup_come_first_and_once(settings_module: ModuleType) -> None:
    settings_module.INSTALLED_APPS.append(WIREUP_APPLICATION)

    configure(settings_module)

    assert settings_module.INSTALLED_APPS == [APPLICATION, "tests.django_application.service", WIREUP_APPLICATION]
    assert settings_module.MIDDLEWARE == [WIREUP_MIDDLEWARE, "django.middleware.common.CommonMiddleware"]


def test_the_container_holds_the_component_scan_and_the_django_sections_read(settings_module: ModuleType) -> None:
    configure(settings_module)

    injectables = settings_module.WIREUP.injectables
    assert set(CONTAINER.module_names()) <= set(injectables)
    assert DjangoProperties.__module__ in injectables
    assert DatabaseProperties.__module__ in injectables
    assert settings_module.WIREUP.auto_inject_views is False


def test_when_django_starts_the_sections_of_the_container_are_read(settings_module: ModuleType) -> None:
    configure(settings_module)

    complete_configuration(settings_module)

    assert configuration_of(settings_module).get(GreetingProperties).text == "Hello"


def test_an_adapter_receives_its_section_from_the_container(settings_module: ModuleType) -> None:
    configure(settings_module)
    complete_configuration(settings_module)
    configuration = configuration_of(settings_module)

    container = wireup.create_sync_container(
        injectables=[import_module(name) for name in settings_module.WIREUP.injectables],
        config={CONFIGURATION_KEY: configuration},
    )

    assert container.get(GreetingProperties) is configuration.get(GreetingProperties)
    assert container.get(DjangoProperties) is configuration.get(DjangoProperties)


def test_a_table_no_module_of_the_container_claims_stops_the_start(settings_module: ModuleType) -> None:
    configure(settings_module, component_scan=CONTAINER_WITHOUT_SECTIONS)

    with pytest.raises(ValidationError, match="greeting"):
        complete_configuration(settings_module)


def test_without_configure_django_the_start_stops(settings_module: ModuleType) -> None:
    with pytest.raises(ImproperlyConfigured, match="call configure_django"):
        complete_configuration(settings_module)
