"""The sections Django itself needs: `[django]`, `[database]` and `[cache]` become Django settings in one line each."""

from snakeboot.configuration import (
    CacheProperties,
    Configuration,
    DatabaseProperties,
    DjangoProperties,
    load_configuration,
)

DJANGO_SERVICE = "tests.configuration.django_service"


def load_django_service() -> Configuration:
    return load_configuration(DjangoProperties, DatabaseProperties, CacheProperties, package=DJANGO_SERVICE)


def test_the_database_section_is_an_entry_of_databases() -> None:
    database = load_django_service().get(DatabaseProperties)

    assert database.as_django_database() == {
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

    assert cache.as_django_cache() == {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://redis:6379/1",
    }
