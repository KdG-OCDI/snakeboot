import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from snakeboot.actuator.health_indicator import HealthIndicator, Status

logger = logging.getLogger(__name__)


class InvalidHealthIndicatorError(TypeError):
    """Raised at start-up when two health indicators answer under one name: `/health` could not tell them apart."""


@dataclass(frozen=True, slots=True)
class HealthReport:
    """The health of the application: UP when every part is, and the status of each part by name."""

    status: Status
    components: Mapping[str, Status]


class ApplicationHealth:
    """Asks every `HealthIndicator` of the application how its part is, like Spring Boot's `HealthEndpoint`.

    The application is UP when every part is; a part whose check raises is DOWN, and what it raised is logged, not
    answered, as Spring Boot shows no details by default. Without indicators the application is UP.
    """

    def __init__(self, indicators: Iterable[HealthIndicator]) -> None:
        self._indicators = sorted(indicators, key=lambda indicator: indicator.name)
        names = [indicator.name for indicator in self._indicators]
        if twice := sorted({name for name in names if names.count(name) > 1}):
            raise InvalidHealthIndicatorError(f"Two health indicators are named {', '.join(twice)}.")

    def report(self) -> HealthReport:
        """Checks every part now and reports the health of the application."""
        components = {indicator.name: _status_of(indicator) for indicator in self._indicators}
        healthy = all(status is Status.UP for status in components.values())
        return HealthReport(Status.UP if healthy else Status.DOWN, components)


def _status_of(indicator: HealthIndicator) -> Status:
    try:
        indicator.check()
    except Exception as error:  # noqa: BLE001  # reason: whatever a check raises, its part is down
        logger.warning("The health check of %s failed: %r", indicator.name, error)
        return Status.DOWN
    return Status.UP
