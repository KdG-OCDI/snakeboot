"""An async scheduled method, which the scheduler's thread cannot await."""

from datetime import timedelta

from snakeboot.scheduling import scheduled


class Asynchronous:
    """Stands in for a mistake: scheduled methods are synchronous."""

    @scheduled(fixed_delay=timedelta(seconds=1))
    async def run(self) -> None:
        """Cannot be scheduled."""
