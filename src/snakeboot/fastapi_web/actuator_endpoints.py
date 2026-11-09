from collections.abc import Callable
from typing import Final

from fastapi import FastAPI
from starlette.responses import JSONResponse, PlainTextResponse, Response

from snakeboot.actuator import CONTENT_TYPE, Actuator, Status

HEALTH_PATH: Final = "/health"
"""The health of the application: every indicator, 200 when all are UP and 503 otherwise. Outside the API, without a
token, like Spring Boot's `/actuator/health`."""

LIVENESS_PATH: Final = "/health/liveness"
"""Whether the process lives: UP while it answers, whatever its parts say. Kubernetes's livenessProbe; a failing
database must not restart every replica."""

READINESS_PATH: Final = "/health/readiness"
"""Whether the process can serve: as `/health`. Kubernetes's readinessProbe takes it out of the load balancer while a
part it needs is DOWN."""

METRICS_PATH: Final = "/metrics"
"""The metrics in Prometheus's text format, like Spring Boot's `/actuator/prometheus`; Prometheus's own default path."""


def add_actuator(api: FastAPI, service: str, actuator: Actuator) -> None:
    """Serves the health and the metrics of `actuator` beside the API, outside the OpenAPI document."""
    health = _health_of(service, actuator)
    api.add_api_route(HEALTH_PATH, health, methods=["GET"], include_in_schema=False)
    api.add_api_route(LIVENESS_PATH, _alive, methods=["GET"], include_in_schema=False)
    api.add_api_route(READINESS_PATH, health, methods=["GET"], include_in_schema=False)
    api.add_api_route(METRICS_PATH, _metrics_of(actuator), methods=["GET"], include_in_schema=False)


def _health_of(service: str, actuator: Actuator) -> Callable[[], Response]:
    def health() -> Response:
        report = actuator.health.report()
        body = {
            "status": report.status.value,
            "service": service,
            "components": {name: {"status": status.value} for name, status in report.components.items()},
        }
        return JSONResponse(body, status_code=200 if report.status is Status.UP else 503)

    return health


def _alive() -> dict[str, str]:
    return {"status": Status.UP.value}


def _metrics_of(actuator: Actuator) -> Callable[[], Response]:
    def metrics() -> Response:
        return PlainTextResponse(actuator.meters.scrape(), media_type=CONTENT_TYPE)

    return metrics
