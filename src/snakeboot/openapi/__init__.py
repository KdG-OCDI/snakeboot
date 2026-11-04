"""Technical library: the description of an application's API (standard library only).

    @openapi_definition(title="Workshops", version="1.0.0")     # springdoc's @OpenAPIDefinition
    @application_root(base_packages=("workshops",))
    class WorkshopsApplication: ...

It imports nothing but the standard library, so an application class can use it before Django has started: Django
Ninja reads Django's settings when it is imported, and the application class is read while the settings are built.
`snakeboot.rest` shows the description in the OpenAPI document and Swagger UI.
"""

from snakeboot.openapi.openapi_definition import OpenApiDefinition, openapi_definition, openapi_definition_of

__all__ = ["OpenApiDefinition", "openapi_definition", "openapi_definition_of"]
