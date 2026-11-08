import json
from datetime import timedelta
from typing import Any, override

from redis import Redis

from snakeboot.cache import Cache


class RedisCache(Cache):
    """A cache in Redis, like Spring Boot's `RedisCacheManager`: shared by every process of the application.

    A value is stored as JSON under its key; a time to live becomes Redis's own expiry.
    """

    def __init__(self, client: Redis) -> None:
        self._client = client

    @classmethod
    def at(cls, redis_url: str) -> "RedisCache":
        """Returns the cache in the Redis at `redis_url`; it connects at the first call."""
        return cls(Redis.from_url(redis_url))

    @override
    def get(self, key: str) -> Any | None:
        text = self._client.get(key)
        return json.loads(text) if text is not None else None

    @override
    def put(self, key: str, value: Any, *, time_to_live: timedelta | None = None) -> None:
        self._client.set(key, json.dumps(value), ex=time_to_live)

    @override
    def evict(self, key: str) -> None:
        self._client.delete(key)

    def close(self) -> None:
        """Closes the connections to Redis."""
        self._client.close()
