"""An application gets its REST API, described by @openapi_definition, and /health from snakeboot."""

import json

from django.test import RequestFactory
from django.urls import URLPattern

from snakeboot.rest import rest_api, url_patterns
from tests.rest.sample_application import GreetingApplication, UndescribedApplication


def test_the_api_holds_the_controllers_of_the_component_scan() -> None:
    paths = rest_api(GreetingApplication).get_openapi_schema(path_prefix="")["paths"]

    assert set(paths) == {"/greetings/{name}", "/greetings", "/farewells/{name}"}


def test_openapi_definition_describes_the_api() -> None:
    info = rest_api(GreetingApplication).get_openapi_schema(path_prefix="")["info"]

    assert (info["title"], info["version"], info["description"]) == ("Greetings", "2.1.0", "Says hello and goodbye.")


def test_without_openapi_definition_the_api_has_ninja_s_defaults() -> None:
    info = rest_api(UndescribedApplication).get_openapi_schema(path_prefix="")["info"]

    assert info["title"] == "NinjaAPI"


def test_health_answers_with_the_name_of_the_application_package() -> None:
    health = next(pattern for pattern in url_patterns(GreetingApplication) if isinstance(pattern, URLPattern)).callback

    answer = health(RequestFactory().get("/health"))

    assert answer.status_code == 200
    assert json.loads(answer.content) == {"status": "ok", "service": "rest"}
