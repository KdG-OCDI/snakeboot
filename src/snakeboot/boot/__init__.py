"""Where an application starts, like Spring Boot's `SpringApplication`: `run` for its commands, `asgi_application` for
its server.

    # myapp/__main__.py                       # myapp/asgi.py, for uvicorn myapp.asgi:application
    from snakeboot.boot import run            from snakeboot.boot import asgi_application
    run(MyApplication)                        application = asgi_application(MyApplication)

The one place that names the frameworks underneath: FastAPI serves the REST API, SQLAlchemy keeps the entities when
the configuration has `[database]`, pika talks to RabbitMQ when it has `[rabbitmq]`, Redis caches when it has
`[cache]`. An application imports this package and never those frameworks, so a binding to another one changes no
application.
"""

from snakeboot.boot.entry_points import CONDITIONAL_MODULES, asgi_application, run

__all__ = ["CONDITIONAL_MODULES", "asgi_application", "run"]
