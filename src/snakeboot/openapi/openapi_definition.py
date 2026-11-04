from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

OPENAPI_DEFINITION_ATTRIBUTE: Final = "__openapi_definition__"


@dataclass(frozen=True, slots=True)
class OpenApiDefinition:
    """The title, version and description of an application's API, as its OpenAPI document shows them."""

    title: str
    version: str
    description: str


def openapi_definition[C: type](*, title: str, version: str, description: str = "") -> Callable[[C], C]:
    """Describes the API of an application, like springdoc's `@OpenAPIDefinition(info = @Info(...))`.

    Put it on the class marked with `@application_root`; `rest_api` shows it in the OpenAPI document and Swagger UI.
    """
    definition = OpenApiDefinition(title=title, version=version, description=description)

    def declare(application_class: C) -> C:
        setattr(application_class, OPENAPI_DEFINITION_ATTRIBUTE, definition)
        return application_class

    return declare


def openapi_definition_of(application_class: type) -> OpenApiDefinition | None:
    """Returns what `@openapi_definition` declared on `application_class`, or None."""
    definition = vars(application_class).get(OPENAPI_DEFINITION_ATTRIBUTE)
    return definition if isinstance(definition, OpenApiDefinition) else None
