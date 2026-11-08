"""Registers the cache of `[cache]` with wireup.

`snakeboot.boot` adds this module to the container only when the application has a `[cache]` section, like Spring
Boot's `RedisAutoConfiguration` with its conditions: an application without the section imports no Redis client.
"""

from collections.abc import Iterator

from wireup import injectable

from snakeboot.cache import Cache
from snakeboot.configuration import CacheProperties
from snakeboot.redis_cache.redis_cache import RedisCache


@injectable(as_type=Cache)
def redis_cache(properties: CacheProperties) -> Iterator[Cache]:
    """Provides the cache in the Redis of `[cache]`, and closes its connections when the container closes."""
    cache = RedisCache.at(properties.redis_url)
    yield cache
    cache.close()
