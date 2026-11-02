from snakeboot.configuration.configuration_properties import configuration_properties
from snakeboot.configuration.section import Section


@configuration_properties("cache")
class CacheProperties(Section):
    """The section `[cache]`: the Redis that backs Django's cache, like Spring Boot's `spring.data.redis.*`.

    CACHES = {"default": CONFIGURATION.get(CacheProperties).as_django_cache()}
    """

    redis_url: str

    def as_django_cache(self) -> dict[str, str]:
        """The entry of Django's `CACHES` setting."""
        return {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": self.redis_url}
