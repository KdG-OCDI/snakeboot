"""The REST library on Django Ninja: publishes what `snakeboot.rest` finds (extra: snakeboot[ninja]).

The one place that knows Django Ninja. `rest_api(MyApplication)` builds the API from the `ControllerScan` of the
application: one router per controller, an exception handler per error answer, and Ninja's bearer authentication
around the application's `BearerAuthentication`. `snakeboot.django_ninja.urls`, the ROOT_URLCONF that `django_settings`
names, serves it under /api/ with /health beside it. Controllers never see Ninja: another web framework would get a
binding like this one, and no controller would change.
"""

from snakeboot.django_ninja.ninja_endpoint_factory import (
    ComponentResolver,
    NinjaEndpointFactory,
    principal_of,
    resolve_from_wireup_request_scope,
)
from snakeboot.django_ninja.rest_api import BearerToken, add_routes, rest_api, url_patterns

__all__ = [
    "BearerToken",
    "ComponentResolver",
    "NinjaEndpointFactory",
    "add_routes",
    "principal_of",
    "resolve_from_wireup_request_scope",
    "rest_api",
    "url_patterns",
]
