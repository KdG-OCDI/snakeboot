"""Where an application starts, like Spring Boot's `SpringApplication`: `run` runs its commands, its server included.

    # myapp/__main__.py
    from snakeboot.boot import run

    run(MyApplication)                        # python -m myapp serve, python -m myapp migrate, python -m myapp help

The one place that names the frameworks underneath: FastAPI serves the REST API, SQLAlchemy keeps the entities when
the configuration has `[database]`, pika talks to RabbitMQ when it has `[rabbitmq]`, Redis caches when it has
`[cache]`. An application imports this package and never those frameworks, so a binding to another one changes no
application.
"""

from snakeboot.boot.entry_points import CONDITIONAL_MODULES, application_from_environment, asgi_application, run

__all__ = ["CONDITIONAL_MODULES", "application_from_environment", "asgi_application", "run"]
