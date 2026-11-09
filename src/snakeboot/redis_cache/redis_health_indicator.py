from typing import override

from snakeboot.actuator import HealthIndicator
from snakeboot.redis_cache.redis_cache import RedisCache


class RedisHealthIndicator(HealthIndicator, component=False):
    """Checks that Redis answers, like Spring Boot's `RedisHealthIndicator`: it sends `PING`."""

    def __init__(self, cache: RedisCache) -> None:
        self._cache = cache

    @override
    def check(self) -> None:
        self._cache.ping()
