"""Technical library: the health and the metrics of an application, like Spring Boot's actuator.

    class PaymentGatewayHealthIndicator(HealthIndicator):      # a component, like a HealthIndicator bean
        @override
        def check(self) -> None: ...                           # raises when the gateway is down

    self._meters.counter("games_started", "Games started").increment()     # an injected MeterRegistry

The web binding serves `/health` (every indicator: 200 when all are UP, 503 otherwise), `/health/liveness`,
`/health/readiness` and `/metrics` in Prometheus's text format, and times every call. The bindings bring the
indicators of the database, Redis and RabbitMQ. It knows wireup and the standard library only.
"""

from snakeboot.actuator.actuator import Actuator
from snakeboot.actuator.application_health import ApplicationHealth, HealthReport, InvalidHealthIndicatorError
from snakeboot.actuator.health_indicator import HealthIndicator, Status
from snakeboot.actuator.meter_registry import CONTENT_TYPE, Counter, InvalidMeterError, MeterRegistry, Tags, Timer

__all__ = [
    "CONTENT_TYPE",
    "Actuator",
    "ApplicationHealth",
    "Counter",
    "HealthIndicator",
    "HealthReport",
    "InvalidHealthIndicatorError",
    "InvalidMeterError",
    "MeterRegistry",
    "Status",
    "Tags",
    "Timer",
]
