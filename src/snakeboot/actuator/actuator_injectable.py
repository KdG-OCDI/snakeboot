"""Registers the application's health, its metrics and the actuator that serves both with wireup.

Part of snakeboot's auto-configuration (`SNAKEBOOT_AUTO_CONFIGURATION`), like Spring Boot's actuator starter: every
application has a `MeterRegistry` its adapters may inject, and a health with every `HealthIndicator` wireup knows.
"""

from collections.abc import Sequence

from wireup import injectable

from snakeboot.actuator.actuator import Actuator
from snakeboot.actuator.application_health import ApplicationHealth
from snakeboot.actuator.health_indicator import HealthIndicator
from snakeboot.actuator.meter_registry import MeterRegistry


@injectable
def meter_registry() -> MeterRegistry:
    """Provides the one registry of the application's metrics."""
    return MeterRegistry()


@injectable
def application_health(indicators: Sequence[HealthIndicator] = ()) -> ApplicationHealth:
    """Provides the health of every `HealthIndicator` wireup knows; as with the listeners, the default keeps an
    application without indicators starting."""
    return ApplicationHealth(indicators)


@injectable
def actuator(health: ApplicationHealth, meters: MeterRegistry) -> Actuator:
    """Provides what the web binding serves beside the API."""
    return Actuator(health, meters)
