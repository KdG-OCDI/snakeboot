"""Scheduled methods that work, and one that fails every time."""

import threading
from datetime import timedelta

from snakeboot.scheduling import scheduled

QUICKLY = timedelta(milliseconds=10)


class Ticker:
    """Stands in for a job: counts its runs and says when it ran three times."""

    def __init__(self) -> None:
        self.ticks = 0
        self.ticked_three_times = threading.Event()

    @scheduled(fixed_delay=QUICKLY)
    def tick(self) -> None:
        """Runs again shortly after each run."""
        self.ticks += 1
        if self.ticks == 3:
            self.ticked_three_times.set()


class Failing:
    """Stands in for a job whose work always fails, such as one whose database is down."""

    def __init__(self) -> None:
        self.attempts = 0
        self.tried_twice = threading.Event()

    @scheduled(fixed_rate=QUICKLY)
    def fail(self) -> None:
        """Raises at every run."""
        self.attempts += 1
        if self.attempts == 2:
            self.tried_twice.set()
        raise RuntimeError("the database is down")
