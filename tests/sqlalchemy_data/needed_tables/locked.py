"""A scheduled method that one replica at a time runs: it needs the scheduler locks' table."""

from datetime import timedelta

from snakeboot.scheduling import scheduled, scheduler_lock


class Closer:
    @scheduled(fixed_rate=timedelta(minutes=1))
    @scheduler_lock("closer", at_most_for=timedelta(minutes=5))
    def close(self) -> None:
        """Closes what is due, on one replica at a time."""
