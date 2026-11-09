from dataclasses import dataclass, field

from snakeboot.actuator.application_health import ApplicationHealth
from snakeboot.actuator.meter_registry import MeterRegistry


@dataclass(frozen=True, slots=True)
class Actuator:
    """What the web binding serves beside the API, like Spring Boot's actuator: the health and the metrics.

    The container provides the application's (`actuator_injectable`); without one, as in a test of the API alone, the
    health has no indicators and the metrics are the API's own.
    """

    health: ApplicationHealth = field(default_factory=lambda: ApplicationHealth(()))
    meters: MeterRegistry = field(default_factory=MeterRegistry)
