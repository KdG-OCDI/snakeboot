"""Registers the cache of `[cache]` with wireup.

`snakeboot.boot` adds this module to the container only when the application has a `[cache]` section, like Spring
Boot's `RedisAutoConfiguration` with its conditions: an application without the section imports no Redis client.
"""

from collections.abc import Iterator

from wireup import injectable

from snakeboot.actuator import HealthIndicator
from snakeboot.cache import Cache
from snakeboot.configuration import CacheProperties
from snakeboot.redis_cache.redis_cache import RedisCache
from snakeboot.redis_cache.redis_health_indicator import RedisHealthIndicator


@injectable
def redis_cache(properties: CacheProperties) -> Iterator[RedisCache]:
    """Provides the cache in the Redis of `[cache]`, and closes its connections when the container closes."""
    cache = RedisCache.at(properties.redis_url)
    yield cache
    cache.close()


@injectable(as_type=Cache)
def cache(redis: RedisCache) -> Cache:
    """Provides the cache an adapter asks for: the one in Redis."""
    return redis


@injectable(as_type=HealthIndicator, qualifier="snakeboot.redis_cache.RedisHealthIndicator")
def redis_health_indicator(redis: RedisCache) -> HealthIndicator:
    """Provides the check of Redis that `/health` runs."""
    return RedisHealthIndicator(redis)
