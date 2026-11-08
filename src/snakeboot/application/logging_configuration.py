import logging.config

from snakeboot.configuration import ServerProperties


def configure_logging(server: ServerProperties) -> None:
    """Logs to the console from `[server] log_level` up, like Spring Boot's `logging.level.root`.

    pika reports every step of every connection at INFO, and Alembic every plugin it loads; like Spring Boot's
    clients, only their problems show.
    """
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
            "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
            "root": {"handlers": ["console"], "level": server.log_level},
            "loggers": {"pika": {"level": "WARNING"}, "alembic": {"level": "WARNING"}},
        }
    )
