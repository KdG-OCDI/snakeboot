"""The cache library on Redis: `snakeboot.cache` with the server of `[cache]` (extra: snakeboot[cache]).

The one place that knows the Redis client. `snakeboot.boot` adds `redis_cache_injectable` to the container when the
configuration has `[cache]`; an adapter asks for `Cache` and never sees Redis.
"""

from snakeboot.redis_cache.redis_cache import RedisCache

__all__ = ["RedisCache"]
