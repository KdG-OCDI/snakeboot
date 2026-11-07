"""The sections `[database]` and `[cache]` become entries of Django's `DATABASES` and `CACHES`."""

from snakeboot.configuration import (
    CacheProperties,
    Configuration,
    DatabaseProperties,
    ServerProperties,
    load_configuration,
)
from snakeboot.django_application.django_settings import django_cache, django_database

DJANGO_SERVICE = "tests.configuration.django_service"


def load_django_service() -> Configuration:
    return load_configuration(ServerProperties, DatabaseProperties, CacheProperties, package=DJANGO_SERVICE)


def test_the_database_section_is_an_entry_of_databases() -> None:
    database = load_django_service().get(DatabaseProperties)

    assert django_database(database) == {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": "db",
        "PORT": "5432",
        "NAME": "app",
        "USER": "app",
        "PASSWORD": "test-only-password",
    }
    assert "test-only-password" not in repr(database)


def test_the_cache_section_is_an_entry_of_caches() -> None:
    cache = load_django_service().get(CacheProperties)

    assert django_cache(cache) == {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://redis:6379/1",
    }
