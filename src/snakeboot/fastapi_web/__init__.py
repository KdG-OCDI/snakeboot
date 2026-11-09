"""The REST library on FastAPI: publishes what `snakeboot.rest` finds (extra: snakeboot[web]).

The one place that knows FastAPI and Starlette. `rest_api(MyApplication, resolve)` builds the API from the
`ControllerScan` of the application: one router per controller under /api, an exception handler per error answer,
FastAPI's bearer security around the application's `BearerAuthentication` and its `@roles_allowed`, Swagger UI at
/api/docs, the health at /health (with /health/liveness and /health/readiness), the metrics at /metrics, a span of
the caller's trace around every call, and CORS with `[cors]`. Controllers never see FastAPI: another web framework
would get a binding like this one, and no controller would change.
"""

from snakeboot.fastapi_web.actuator_endpoints import HEALTH_PATH, LIVENESS_PATH, METRICS_PATH, READINESS_PATH
from snakeboot.fastapi_web.bearer_token import BearerToken, ComponentResolver
from snakeboot.fastapi_web.event_stream import EventStreamResponse, event_stream_response
from snakeboot.fastapi_web.fastapi_endpoint_factory import FastApiEndpointFactory
from snakeboot.fastapi_web.observation import REQUESTS_METRIC
from snakeboot.fastapi_web.rest_api import API_PREFIX, add_routes, invalid_request_of, rest_api

__all__ = [
    "API_PREFIX",
    "HEALTH_PATH",
    "LIVENESS_PATH",
    "METRICS_PATH",
    "READINESS_PATH",
    "REQUESTS_METRIC",
    "BearerToken",
    "ComponentResolver",
    "EventStreamResponse",
    "FastApiEndpointFactory",
    "add_routes",
    "event_stream_response",
    "invalid_request_of",
    "rest_api",
]
