"""A test component of the notebook: snakeboot finds it in the source and hands it to every `@application_test`."""

from datetime import UTC, datetime, timedelta
from typing import override

from snakeboot.testing import test_component
from tests.pytest_testing.notebook.notes import Clock

START = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)


@test_component(replaces=Clock)
class FixedClock(Clock):
    """A clock that stands still at START until a test moves it on."""

    def __init__(self, now: datetime = START) -> None:
        self._now = now

    @override
    def now(self) -> datetime:
        return self._now

    def advance(self, duration: timedelta) -> None:
        """Moves the clock on by `duration`."""
        self._now += duration
