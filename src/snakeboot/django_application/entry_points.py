import os
import sys
from collections.abc import Sequence
from functools import partial
from importlib import import_module
from typing import Final

from django import setup
from django.core.asgi import get_asgi_application
from django.core.exceptions import ImproperlyConfigured
from django.core.handlers.asgi import ASGIHandler
from django.core.handlers.wsgi import WSGIHandler
from django.core.management import ManagementUtility, get_commands
from django.core.wsgi import get_wsgi_application
from wireup.integration.django import get_app_container

from snakeboot.command_line import CommandLineRunner, command_line_runners, commands_help, run_command
from snakeboot.component_scan import ComponentScan, application_package
from snakeboot.django_application.background_work import DjangoApplicationComponents
from snakeboot.lifecycle.application_lifecycle import ApplicationLifecycle
from snakeboot.lifecycle.lifecycle_asgi_application import LifecycleAsgiApplication

APPLICATION_VARIABLE: Final = "SNAKEBOOT_APPLICATION"
"""The environment variable that names the application class; `run` and the two handlers below set it."""

SETTINGS_MODULE: Final = "snakeboot.django_application.settings"
"""The settings module of every snakeboot application: DJANGO_SETTINGS_MODULE names it."""


HELP: Final = ("help", "--help", "-h")
"""What asks for the help of the program; the help then lists the commands of the application too."""


def run(application: type, argv: Sequence[str] | None = None) -> None:
    """Runs a command of `application`, like Spring Boot's `SpringApplication.run(MyApplication.class)`.

    The entry point of manage.py and of `python -m <package>`: `run(MyApplication)` runs `sys.argv`. A
    `CommandLineRunner` of the component scan runs when the first argument names it (`python -m myapp self_play
    --games 20`, or `help self_play` for its help); every other command is Django's, so `python -m myapp migrate`
    migrates and `python manage.py runserver` serves. A command exits with status 1 on a `CommandLineError`.

    Django starts first: only then does it know every command, those of its apps (`run_lifecycle`) included, and
    a runner with the name of one of them stops the start.
    """
    arguments = list(argv) if argv is not None else list(sys.argv)
    _start(application)
    setup()
    command, command_arguments = _requested_command(arguments)
    runners = _command_line_runners_of(application)
    program = _program_of(application, arguments[0])
    runner = runners.get(command)
    if runner is None:
        _run_django_command(arguments, program)  # Django's commands, help and version, or a command nobody knows
        if command in HELP:
            sys.stdout.write(commands_help(runners))
        return
    build = partial(DjangoApplicationComponents().get, runner)  # only once the arguments are parsed
    if exit_status := run_command(runner, command_arguments, program=program, build=build):
        sys.exit(exit_status)


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


def _requested_command(arguments: Sequence[str]) -> tuple[str, list[str]]:
    # `help self_play` asks for what `self_play --help` prints.
    command, *rest = arguments[1:] or ["help"]
    if command == "help" and rest:
        return rest[0], ["--help"]
    return command, rest


def _command_line_runners_of(application: type) -> dict[str, type[CommandLineRunner]]:
    runners = command_line_runners(ComponentScan.of(application))
    if clashing := sorted(set(runners) & set(get_commands())):
        raise ImproperlyConfigured(
            f"{', '.join(clashing)}: Django has a command of that name already; name the CommandLineRunner otherwise."
        )
    return runners


def _run_django_command(arguments: list[str], program: str) -> None:
    # What execute_from_command_line does, with the program the help should name: Django would say
    # `python -m django` for `python -m myapp`.
    utility = ManagementUtility(arguments)
    utility.prog_name = program
    utility.execute()


def _program_of(application: type, script: str) -> str:
    # `python -m myapp` runs myapp/__main__.py: say so in the help, as Django does for `python -m django`.
    name = os.path.basename(script)
    return f"python -m {application_package(application)}" if name == "__main__.py" else name


def _start(application: type) -> None:
    os.environ[APPLICATION_VARIABLE] = f"{application.__module__}.{application.__qualname__}"
    os.environ["DJANGO_SETTINGS_MODULE"] = SETTINGS_MODULE
