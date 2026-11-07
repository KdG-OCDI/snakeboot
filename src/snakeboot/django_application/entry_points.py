import os
import sys
from collections.abc import Sequence
from importlib import import_module
from typing import Final

from django.core.asgi import get_asgi_application
from django.core.exceptions import ImproperlyConfigured
from django.core.handlers.asgi import ASGIHandler
from django.core.handlers.wsgi import WSGIHandler
from django.core.management import execute_from_command_line
from django.core.wsgi import get_wsgi_application
from wireup.integration.django import get_app_container

from snakeboot.lifecycle.application_lifecycle import ApplicationLifecycle
from snakeboot.lifecycle.lifecycle_asgi_application import LifecycleAsgiApplication

APPLICATION_VARIABLE: Final = "SNAKEBOOT_APPLICATION"
"""The environment variable that names the application class; `run` and the two handlers below set it."""

SETTINGS_MODULE: Final = "snakeboot.django_application.settings"
"""The settings module of every snakeboot application: DJANGO_SETTINGS_MODULE names it."""


def run(application: type, argv: Sequence[str] | None = None) -> None:
    """Runs a Django command of `application`, like Spring Boot's `SpringApplication.run(MyApplication.class)`.

    The entry point of manage.py and of `python -m <package>`: `run(MyApplication)` runs `sys.argv`, so
    `python -m myapp migrate` migrates and `python manage.py runserver` serves.
    """
    _start(application)
    execute_from_command_line(list(argv) if argv is not None else sys.argv)


def wsgi_application(application: type) -> WSGIHandler:
    """Returns the WSGI handler of `application`, for gunicorn: `application = wsgi_application(MyApplication)`.

    WSGI has no moment "the server starts", so no lifecycle runs: an application with `@scheduled` or
    `@rabbit_listener` methods uses `asgi_application`, or runs them apart with `run_lifecycle`.
    """
    _start(application)
    return get_wsgi_application()


def asgi_application(application: type) -> LifecycleAsgiApplication:
    """Returns the ASGI application of `application`, for uvicorn: `application = asgi_application(MyApplication)`.

    Django's handler serves the requests; around it, the application's lifecycle starts and stops with the server
    (uvicorn's `lifespan`), so `@scheduled` and `@rabbit_listener` methods run while it serves. Under ASGI a response
    can also stream from an async iterator, such as server-sent events, without holding a thread.
    """
    _start(application)
    handler: ASGIHandler = get_asgi_application()
    return LifecycleAsgiApplication(handler, lifecycle=_application_lifecycle)


def application_named_in_environment() -> type:
    """Returns the application class that `run` or `wsgi_application` named; without one, the start stops."""
    name = os.environ.get(APPLICATION_VARIABLE, "")
    module_name, _, class_name = name.rpartition(".")
    application = getattr(import_module(module_name), class_name, None) if module_name else None
    if not isinstance(application, type):
        raise ImproperlyConfigured(
            f"{APPLICATION_VARIABLE}={name!r} names no application class. Start the application with snakeboot's "
            "run(MyApplication), wsgi_application(MyApplication) or asgi_application(MyApplication)."
        )
    return application


async def _application_lifecycle() -> ApplicationLifecycle:
    # Asked for when the server starts: by then get_asgi_application() has set Django up, and wireup its container.
    lifecycle: ApplicationLifecycle = await get_app_container().get(ApplicationLifecycle)
    return lifecycle


def _start(application: type) -> None:
    os.environ[APPLICATION_VARIABLE] = f"{application.__module__}.{application.__qualname__}"
    os.environ["DJANGO_SETTINGS_MODULE"] = SETTINGS_MODULE
