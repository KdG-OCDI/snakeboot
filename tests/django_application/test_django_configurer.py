"""A `DjangoConfigurer` adds Django apps and middleware from outside the project, found like an AppConfig."""

import pytest
from django.core.exceptions import ImproperlyConfigured

from snakeboot.django_application import APPLICATION, django_settings
from snakeboot.django_application.installed_apps import COMMON_MIDDLEWARE, WIREUP_APPLICATION, WIREUP_MIDDLEWARE
from tests.django_application.service.applications import ServiceApplication
from tests.django_application.service_with_configurers.applications import (
    AppAddedTwiceApplication,
    ConfiguredApplication,
)


def test_a_configurer_adds_its_apps_after_the_app_configs_of_the_scan() -> None:
    assert django_settings(ConfiguredApplication)["INSTALLED_APPS"] == [APPLICATION, WIREUP_APPLICATION, "corsheaders"]


def test_the_middleware_of_the_configurers_comes_between_wireup_and_common_middleware() -> None:
    # The configurers come in the order of their dotted paths: the one of the scan, then the one of the service.
    assert django_settings(ConfiguredApplication)["MIDDLEWARE"] == [
        WIREUP_MIDDLEWARE,
        "corsheaders.middleware.CorsMiddleware",
        "django.middleware.security.SecurityMiddleware",
        COMMON_MIDDLEWARE,
    ]


def test_without_configurers_the_middleware_is_wireup_and_common_middleware() -> None:
    assert django_settings(ServiceApplication)["MIDDLEWARE"] == [WIREUP_MIDDLEWARE, COMMON_MIDDLEWARE]


def test_an_app_added_although_the_scan_finds_it_stops_the_start() -> None:
    with pytest.raises(ImproperlyConfigured, match=r"TwiceConfigurer adds .* but the component scan finds it already"):
        django_settings(AppAddedTwiceApplication)
