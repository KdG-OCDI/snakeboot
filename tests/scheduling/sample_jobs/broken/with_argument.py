"""A scheduled method that wants an argument the scheduler cannot give."""

from datetime import timedelta

from snakeboot.scheduling import scheduled


class WantsAnArgument:
    """Stands in for a mistake: a scheduled method gets nothing but self."""

    @scheduled(fixed_delay=timedelta(seconds=1))
    def run(self, when: str) -> None:
        """Cannot be scheduled."""
