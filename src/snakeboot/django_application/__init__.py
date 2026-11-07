"""Django integration of the application: its settings, its container and its start (extras `configuration`, `django`).

An application starts through `snakeboot.boot`, which hands `run`, `wsgi_application` and `asgi_application` over
from here; only snakeboot itself, and a test that needs Django's settings, import this package.

Like Spring Boot, the application writes no settings: snakeboot builds them from the application class and its
application.toml (`django_settings`). `run` runs the application's `CommandLineRunner`s and Django's own commands.
When Django starts, this app reads the sections declared in the modules of the container and, with a database,
installs the transaction manager of `@transactional`. A `DjangoConfigurer` in the scan adds Django apps and
middleware from outside the project.
"""

from snakeboot.django_application.django_configurer import DjangoConfigurer
from snakeboot.django_application.django_settings import APPLICATION_SETTING, django_settings
from snakeboot.django_application.entry_points import (
    APPLICATION_VARIABLE,
    SETTINGS_MODULE,
    asgi_application,
    run,
    wsgi_application,
)
from snakeboot.django_application.installed_apps import APPLICATION

__all__ = [
    "APPLICATION",
    "APPLICATION_SETTING",
    "APPLICATION_VARIABLE",
    "SETTINGS_MODULE",
    "DjangoConfigurer",
    "asgi_application",
    "django_settings",
    "run",
    "wsgi_application",
]
