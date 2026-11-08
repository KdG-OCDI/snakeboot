"""A cache keeps JSON values by key for a while: in memory for a test, in Redis for the application."""

from datetime import timedelta
from typing import Any

from snakeboot.cache import InMemoryCache
from snakeboot.redis_cache import RedisCache


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_a_value_is_kept_under_its_key_until_it_is_evicted() -> None:
    cache = InMemoryCache()

    cache.put("question", {"text": "Hallo", "sources": ["rules.md"]})

    assert cache.get("question") == {"text": "Hallo", "sources": ["rules.md"]}
    cache.evict("question")
    assert cache.get("question") is None


def test_a_value_expires_after_its_time_to_live() -> None:
    clock = Clock()
    cache = InMemoryCache(clock)
    cache.put("question", "answer", time_to_live=timedelta(seconds=10))

    clock.now = 9.9
    assert cache.get("question") == "answer"
    clock.now = 10.0
    assert cache.get("question") is None


def test_a_kept_value_does_not_change_with_the_caller_s() -> None:
    cache = InMemoryCache()
    value = {"sources": ["rules.md"]}
    cache.put("question", value)

    value["sources"].append("faq.md")

    assert cache.get("question") == {"sources": ["rules.md"]}


class FakeRedis:
    """Stands in for redis-py's client: remembers what it was told."""

    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.expiries: dict[str, timedelta | None] = {}
        self.closed = False

    def get(self, key: str) -> bytes | None:
        value = self.values.get(key)
        return value.encode() if isinstance(value, str) else value

    def set(self, key: str, value: str, ex: timedelta | None = None) -> None:
        self.values[key], self.expiries[key] = value, ex

    def delete(self, key: str) -> None:
        self.values.pop(key, None)

    def close(self) -> None:
        self.closed = True


def test_redis_keeps_a_value_as_json_with_redis_s_own_expiry() -> None:
    client = FakeRedis()
    cache = RedisCache(client)  # type: ignore[arg-type]

    cache.put("question", {"text": "Hallo"}, time_to_live=timedelta(hours=1))

    assert client.values == {"question": '{"text": "Hallo"}'}
    assert client.expiries == {"question": timedelta(hours=1)}
    assert cache.get("question") == {"text": "Hallo"}


def test_redis_forgets_and_closes() -> None:
    client = FakeRedis()
    cache = RedisCache(client)  # type: ignore[arg-type]
    cache.put("question", "answer")

    cache.evict("question")
    cache.close()

    assert (cache.get("question"), client.closed) == (None, True)
