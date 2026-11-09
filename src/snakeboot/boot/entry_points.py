import os
from collections.abc import Sequence
from functools import reduce
from importlib import import_module
from typing import TYPE_CHECKING, Final

from snakeboot.actuator import Actuator
from snakeboot.application import ApplicationContext, ConditionalModules, run_application
from snakeboot.configuration import (
    CacheProperties,
    CorsProperties,
    DatabaseProperties,
    RabbitProperties,
    ServerProperties,
)
from snakeboot.lifecycle.application_lifecycle import ApplicationLifecycle
from snakeboot.lifecycle.lifecycle_asgi_application import LifecycleAsgiApplication

if TYPE_CHECKING:
    from fastapi import FastAPI

CONDITIONAL_MODULES: Final[ConditionalModules] = {
    ServerProperties: ("snakeboot.boot.serve_command",),
    DatabaseProperties: (
        "snakeboot.sqlalchemy_data.sqlalchemy_data_injectable",
        "snakeboot.sqlalchemy_data.migration_commands",
        "snakeboot.event_publication.event_publication_record",
        "snakeboot.event_publication.event_publication_injectable",
        "snakeboot.scheduler_lock.scheduler_lock_record",
        "snakeboot.scheduler_lock.scheduler_lock_injectable",
    ),
    RabbitProperties: ("snakeboot.rabbitmq.rabbitmq_injectable",),
    CacheProperties: ("snakeboot.redis_cache.redis_cache_injectable",),
}
"""Which binding joins the container for which table, like Spring Boot's conditional auto-configuration.

`[server]` brings `serve`. `[database]` brings the event publication registry of the `@application_module_listener`
methods and the locks of `@scheduler_lock` with it. An application without `[database]` imports no SQLAlchemy, one
without `[rabbitmq]` no pika, one without `[cache]` no Redis client.
"""

APPLICATION_VARIABLE: Final = "SNAKEBOOT_APPLICATION"
"""The environment variable through which `serve` names the application class to the processes uvicorn starts."""


def run(application: type, argv: Sequence[str] | None = None) -> None:
    """Runs a command of `application`, like Spring Boot's `SpringApplication.run(MyApplication.class, args)`.

    The entry point of `python -m myapp`: `run(MyApplication)` runs `sys.argv`. The first argument names a
    `CommandLineRunner` of the component scan, or one of snakeboot's own: `serve` for the web server,
    `run_lifecycle` without one, and with a database `migrate` and `make_migration`. `help` lists them all.
    """
    run_application(application, argv, CONDITIONAL_MODULES)


def asgi_application(application: type) -> LifecycleAsgiApplication:
    """Returns the ASGI application of `application`, which `serve` runs in each of its processes.

    An application needs nothing of it: `python -m myapp serve` starts the server. A deployment that runs an ASGI
    server of its own points it at a module that holds `application = asgi_application(MyApplication)`.

    The application starts here: its configuration, its container and its transactions. FastAPI serves its REST API;
    around it, the application's lifecycle starts and stops with the server (uvicorn's `lifespan`), so `@scheduled`
    and `@rabbit_listener` methods run while it serves.
    """
    context = ApplicationContext.start(application, CONDITIONAL_MODULES)

    async def lifecycle() -> ApplicationLifecycle:
        return context.get(ApplicationLifecycle)

    return LifecycleAsgiApplication(web_api(context), lifecycle=lifecycle)


def application_from_environment() -> LifecycleAsgiApplication:
    """Returns the ASGI application that `SNAKEBOOT_APPLICATION` names: uvicorn's factory in each process of `serve`."""
    named = os.environ.get(APPLICATION_VARIABLE, "")
    module_name, _, class_name = named.partition(":")
    try:
        application = reduce(getattr, class_name.split("."), import_module(module_name))
    except (ImportError, AttributeError, ValueError) as error:
        raise LookupError(
            f"{APPLICATION_VARIABLE}={named!r} names no application class: start it with serve."
        ) from error
    if not isinstance(application, type):
        raise LookupError(f"{APPLICATION_VARIABLE}={named!r} names {application!r}, which is no class.")
    return asgi_application(application)


def application_variable_of(application: type) -> str:
    """Returns `module:Class`, how `SNAKEBOOT_APPLICATION` names `application`."""
    return f"{application.__module__}:{application.__qualname__}"


def web_api(context: ApplicationContext) -> "FastAPI":
    """Returns the REST API of a started application, with its `[server]`, its `[cors]` and its actuator."""
    # Imported here: a process that only runs a command needs no web framework.
    from snakeboot.fastapi_web import rest_api  # noqa: PLC0415  # reason: FastAPI loads only for the server

    configuration = context.configuration
    return rest_api(
        context.application,
        context.get,
        server=configuration.get(ServerProperties),
        cors=configuration.get(CorsProperties) if CorsProperties in configuration.sections else None,
        actuator=context.get(Actuator),
    )
