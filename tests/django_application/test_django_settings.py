"""`django_settings` builds every Django setting of an application from its application root and application.toml."""

from importlib import import_module
from types import SimpleNamespace
from typing import Any

import pytest
import wireup
from django.core.exceptions import ImproperlyConfigured
from pydantic import ValidationError

from snakeboot.configuration import (
    CONFIGURATION_KEY,
    Configuration,
    DatabaseProperties,
    DjangoProperties,
    OAuth2Properties,
)
from snakeboot.django_application import APPLICATION, APPLICATION_SETTING, django_settings
from snakeboot.django_application.container_sections import complete_configuration
from snakeboot.django_application.installed_apps import WIREUP_APPLICATION
from tests.django_application.container.greeting_properties import GreetingProperties
from tests.django_application.service.applications import (
    ServiceApplication,
    ServiceWithALooseModelApplication,
    ServiceWithAModelApplication,
    ServiceWithoutSectionsApplication,
)
from tests.django_application.service_with_oauth2.applications import ServiceWithOAuth2Application
from tests.django_application.service_without_database.applications import ServiceWithoutDatabaseApplication

GREETING_PERSISTENCE_CONFIG = (
    "tests.django_application.container_with_a_model.persistence.apps.GreetingPersistenceConfig"
)


def configuration_of(settings: dict[str, Any]) -> Configuration:
    configuration = settings[CONFIGURATION_KEY]
    assert isinstance(configuration, Configuration)
    return configuration


def test_the_django_settings_come_from_the_django_table() -> None:
    settings = django_settings(ServiceApplication)

    assert settings["SECRET_KEY"] == "test-only-secret"
    assert settings["DEBUG"] is False
    assert settings["ALLOWED_HOSTS"] == ["greeting.example"]
    assert settings["LOGGING"]["root"]["level"] == "WARNING"


def test_application_toml_lies_in_the_package_of_the_application_class() -> None:
    assert django_settings(ServiceWithoutDatabaseApplication)["DEBUG"] is True


def test_the_database_table_becomes_databases() -> None:
    settings = django_settings(ServiceApplication)

    assert settings["DATABASES"]["default"]["HOST"] == "db"
    assert "CACHES" not in settings


def test_without_a_database_table_there_are_no_databases() -> None:
    assert "DATABASES" not in django_settings(ServiceWithoutDatabaseApplication)


def test_the_settings_name_the_application_and_snakeboot_s_urls() -> None:
    settings = django_settings(ServiceApplication)

    assert settings[APPLICATION_SETTING] is ServiceApplication
    assert settings["ROOT_URLCONF"] == "snakeboot.rest.urls"
    assert (settings["USE_TZ"], settings["TIME_ZONE"]) == (True, "UTC")


def test_the_container_holds_the_component_scan_and_the_django_sections_read() -> None:
    settings = django_settings(ServiceApplication)

    injectables = settings["WIREUP"].injectables
    assert "tests.django_application.container.greeting_properties" in injectables
    assert DjangoProperties.__module__ in injectables
    assert DatabaseProperties.__module__ in injectables
    assert settings["WIREUP"].auto_inject_views is False
    assert settings["MIDDLEWARE"][0] == "wireup.integration.django.wireup_middleware"


def test_the_django_apps_are_snakeboot_wireup_and_the_app_configs_of_the_scan() -> None:
    settings = django_settings(ServiceWithAModelApplication)

    assert settings["INSTALLED_APPS"] == [APPLICATION, WIREUP_APPLICATION, GREETING_PERSISTENCE_CONFIG]


def test_a_model_outside_every_app_stops_the_start() -> None:
    with pytest.raises(ImproperlyConfigured, match=r"LooseOrmEntity is a Django model outside every app"):
        django_settings(ServiceWithALooseModelApplication)


def test_when_django_starts_the_sections_of_the_container_are_read() -> None:
    settings = django_settings(ServiceApplication)

    complete_configuration(SimpleNamespace(**settings))

    assert configuration_of(settings).get(GreetingProperties).text == "Hello"


def test_an_adapter_receives_its_section_from_the_container() -> None:
    settings = django_settings(ServiceApplication)
    complete_configuration(SimpleNamespace(**settings))
    configuration = configuration_of(settings)

    container = wireup.create_sync_container(
        injectables=[import_module(name) for name in settings["WIREUP"].injectables],
        config={CONFIGURATION_KEY: configuration},
    )

    assert container.get(GreetingProperties) is configuration.get(GreetingProperties)
    assert container.get(DjangoProperties) is configuration.get(DjangoProperties)


def test_a_table_no_module_of_the_container_claims_stops_the_start() -> None:
    settings = django_settings(ServiceWithoutSectionsApplication)

    with pytest.raises(ValidationError, match="greeting"):
        complete_configuration(SimpleNamespace(**settings))


def test_without_the_settings_of_snakeboot_the_start_stops() -> None:
    with pytest.raises(ImproperlyConfigured, match="start the application with snakeboot's run"):
        complete_configuration(SimpleNamespace())


def test_the_oauth2_table_is_read_and_its_section_joins_the_container() -> None:
    settings = django_settings(ServiceWithOAuth2Application)

    assert configuration_of(settings).get(OAuth2Properties).audience == "greeting"
    assert OAuth2Properties.__module__ in settings["WIREUP"].injectables


def test_without_an_oauth2_table_there_is_no_oauth2_section() -> None:
    assert OAuth2Properties not in configuration_of(django_settings(ServiceApplication)).sections
