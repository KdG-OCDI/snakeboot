"""Technical library: a cache of JSON values, like Spring's `Cache` (standard library only).

    class AnswerCache:                                  # an adapter of the application
        def __init__(self, cache: Cache) -> None: ...   # the component, when the configuration has [cache]

        def remember(self, question: str, answer: dict[str, str]) -> None:
            self._cache.put(question, answer, time_to_live=timedelta(hours=1))

An adapter asks for `Cache` by type. With a `[cache]` table, `snakeboot.redis_cache` provides one on Redis; a test
gives an `InMemoryCache`.
"""

from snakeboot.cache.cache import Cache
from snakeboot.cache.in_memory_cache import InMemoryCache

__all__ = ["Cache", "InMemoryCache"]
