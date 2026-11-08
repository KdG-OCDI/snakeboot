from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Any


class Cache(ABC):
    """Values kept by key for a while, like Spring's `Cache`: what is cheap to forget and costly to compute again.

    A value is anything JSON can hold (dicts, lists, text, numbers), so every cache keeps it alike, in memory or in
    Redis. A value may be gone at any moment: a caller always knows how to compute it again.
    """

    @abstractmethod
    def get(self, key: str) -> Any | None:
        """Returns the value kept under `key`, or None when there is none or it expired."""

    @abstractmethod
    def put(self, key: str, value: Any, *, time_to_live: timedelta | None = None) -> None:
        """Keeps `value` under `key`, for `time_to_live` or until it is evicted."""

    @abstractmethod
    def evict(self, key: str) -> None:
        """Forgets the value under `key`, if there is one."""
