import json
import threading
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any, override

from snakeboot.cache.cache import Cache


class InMemoryCache(Cache):
    """A cache in this process's memory, like Spring's `ConcurrentMapCache`: for tests and a single process.

    It keeps a JSON copy of each value, as Redis would, so a test sees what a value looks like after the round trip
    and a caller cannot change a kept value by changing its own.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._values: dict[str, tuple[str, float | None]] = {}
        self._lock = threading.Lock()

    @override
    def get(self, key: str) -> Any | None:
        with self._lock:
            kept = self._values.get(key)
            if kept is None:
                return None
            text, expires_at = kept
            if expires_at is not None and self._clock() >= expires_at:
                del self._values[key]
                return None
        return json.loads(text)

    @override
    def put(self, key: str, value: Any, *, time_to_live: timedelta | None = None) -> None:
        expires_at = self._clock() + time_to_live.total_seconds() if time_to_live is not None else None
        with self._lock:
            self._values[key] = (json.dumps(value), expires_at)

    @override
    def evict(self, key: str) -> None:
        with self._lock:
            self._values.pop(key, None)
