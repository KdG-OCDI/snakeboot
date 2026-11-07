from typing import Any, Final

from wireup.integration.django import WireupSettings

from snakeboot.component_scan import ComponentScan, application_package
from snakeboot.configuration import (
    CONFIGURATION_KEY,
    CacheProperties,
    Configuration,
    DatabaseProperties,
    DjangoProperties,
    OAuth2Properties,
    RabbitProperties,
    SchedulingProperties,
    begin_configuration,
)
from snakeboot.django_application.django_configurer import configurers_in
from snakeboot.django_application.installed_apps import installed_apps, middleware

APPLICATION_SETTING: Final = "APPLICATION"
"""The setting that holds the class marked with `@application_root`, for the URLs and the tests."""

URL_CONFIGURATION: Final = "snakeboot.rest.urls"

RABBITMQ_AUTO_CONFIGURATION: Final = "snakeboot.rabbitmq.rabbitmq_injectable"
"""The module that brings RabbitMQ into the container, only when the application has `[rabbitmq]`: by name, so an
application without the section imports no pika."""


def django_settings(application: type) -> dict[str, Any]:
    """Returns every Django setting of `application`, built from its `@application_root` and its application.toml.

    Like Spring Boot's auto-configuration, the application writes no settings of its own:

        SECRET_KEY, DEBUG, ALLOWED_HOSTS, LOGGING    from [django]
        DATABASES                                    from [database], when the application has that table
        CACHES                                       from [cache], when the application has that table
        CONFIGURATION                                the sections read, completed when Django starts; [oauth2],
                                                     when there, for a JwtBearerAuthentication
        WIREUP                                       the container: the modules of the component scan, and
                                                     RabbitMQ's listeners and template when [rabbitmq] is there
        INSTALLED_APPS                               snakeboot, wireup, every AppConfig, and what DjangoConfigurers add
        MIDDLEWARE                                   wireup's, what DjangoConfigurers add, then CommonMiddleware
        TEMPLATES, ROOT_URLCONF                      Swagger UI's templates and snakeboot's URLs
        USE_TZ, TIME_ZONE                            aware datetimes in UTC
        APPLICATION                                  the application class itself

    The AppConfigs and DjangoConfigurers come from the component scan and from the package of the application
    class, where application.toml lies too. A test that needs a double, such as SQLite for
    PostgreSQL, takes these settings and replaces that one setting.
    """
    component_scan = ComponentScan.of(application)
    scans = (component_scan, ComponentScan((application_package(application),), auto_configuration=()))
    configurers = configurers_in(scans)
    configuration = begin_configuration(
        DjangoProperties,
        optional=(DatabaseProperties, CacheProperties, OAuth2Properties, RabbitProperties, SchedulingProperties),
        package=application_package(application),
    )
    return {
        APPLICATION_SETTING: application,
        CONFIGURATION_KEY: configuration,
        **_django_values(configuration.get(DjangoProperties)),
        **_infrastructure(configuration),
        "WIREUP": _container_of(configuration, component_scan),
        "INSTALLED_APPS": installed_apps(scans, configurers),
        "MIDDLEWARE": middleware(configurers),
        # Swagger UI at /api/docs is a Django template; Django Ninja ships it without being an installed app.
        "TEMPLATES": [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [], "APP_DIRS": False}],
        "ROOT_URLCONF": URL_CONFIGURATION,
        "USE_TZ": True,
        "TIME_ZONE": "UTC",
    }


def _django_values(django: DjangoProperties) -> dict[str, Any]:
    return {
        "SECRET_KEY": django.secret_key.get_secret_value(),
        "DEBUG": django.debug,
        "ALLOWED_HOSTS": list(django.allowed_hosts),
        "LOGGING": {
            "version": 1,
            "disable_existing_loggers": False,
            "handlers": {"console": {"class": "logging.StreamHandler"}},
            "root": {"handlers": ["console"], "level": django.log_level},
            # pika reports every step of every connection at INFO; like Spring Boot's AMQP client, only problems.
            "loggers": {"pika": {"level": "WARNING"}},
        },
    }


def _infrastructure(configuration: Configuration) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if DatabaseProperties in configuration.sections:
        values["DATABASES"] = {"default": configuration.get(DatabaseProperties).as_django_database()}
    if CacheProperties in configuration.sections:
        values["CACHES"] = {"default": configuration.get(CacheProperties).as_django_cache()}
    return values


def _container_of(configuration: Configuration, component_scan: ComponentScan) -> WireupSettings:
    # Django's own sections are declared in snakeboot, outside the scan: their modules join the container too.
    modules = [*component_scan.module_names(), *(section.__module__ for section in configuration.sections)]
    if RabbitProperties in configuration.sections:
        modules.append(RABBITMQ_AUTO_CONFIGURATION)
    return WireupSettings(injectables=list(dict.fromkeys(modules)), auto_inject_views=False)
