from collections.abc import Sequence
from typing import TYPE_CHECKING, Final

from snakeboot.application import ApplicationContext, ConditionalModules, run_application
from snakeboot.configuration import CacheProperties, DatabaseProperties, RabbitProperties, ServerProperties
from snakeboot.lifecycle.application_lifecycle import ApplicationLifecycle
from snakeboot.lifecycle.lifecycle_asgi_application import LifecycleAsgiApplication

if TYPE_CHECKING:
    from fastapi import FastAPI

CONDITIONAL_MODULES: Final[ConditionalModules] = {
    DatabaseProperties: (
        "snakeboot.sqlalchemy_data.sqlalchemy_data_injectable",
        "snakeboot.sqlalchemy_data.migration_commands",
    ),
    RabbitProperties: ("snakeboot.rabbitmq.rabbitmq_injectable",),
    CacheProperties: ("snakeboot.redis_cache.redis_cache_injectable",),
}
"""Which binding joins the container for which table, like Spring Boot's conditional auto-configuration.

An application without `[database]` imports no SQLAlchemy, one without `[rabbitmq]` no pika, one without `[cache]`
no Redis client.
"""


def run(application: type, argv: Sequence[str] | None = None) -> None:
    """Runs a command of `application`, like Spring Boot's `SpringApplication.run(MyApplication.class, args)`.

    The entry point of `python -m myapp`: `run(MyApplication)` runs `sys.argv`. The first argument names a
    `CommandLineRunner` of the component scan, or one of snakeboot's own: `run_lifecycle` without a web server, and
    with a database `migrate` and `make_migration`. `help` lists them all.
    """
    run_application(application, argv, CONDITIONAL_MODULES)


def asgi_application(application: type) -> LifecycleAsgiApplication:
    """Returns the ASGI application of `application`, for uvicorn: `application = asgi_application(MyApplication)`.

    The application starts here: its configuration, its container and its transactions. FastAPI serves its REST API;
    around it, the application's lifecycle starts and stops with the server (uvicorn's `lifespan`), so `@scheduled`
    and `@rabbit_listener` methods run while it serves.
    """
    context = ApplicationContext.start(application, CONDITIONAL_MODULES)

    async def lifecycle() -> ApplicationLifecycle:
        return context.get(ApplicationLifecycle)

    return LifecycleAsgiApplication(_web_api(context), lifecycle=lifecycle)


def _web_api(context: ApplicationContext) -> "FastAPI":
    # Imported here: a process that only runs a command needs no web framework.
    from snakeboot.fastapi_web import rest_api  # noqa: PLC0415  # reason: FastAPI loads only for the server

    return rest_api(context.application, context.get, server=context.configuration.get(ServerProperties))
