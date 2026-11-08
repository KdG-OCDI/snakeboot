"""Technical library: the description of an application's API (standard library only).

    @openapi_definition(title="Workshops", version="1.0.0")     # springdoc's @OpenAPIDefinition
    @application_root(base_packages=("workshops",))
    class WorkshopsApplication: ...

It imports nothing but the standard library, so an application class can use it before any framework has
started: the application class is read before the container and the web framework exist.
`snakeboot.rest` shows the description in the OpenAPI document and Swagger UI.
"""

from snakeboot.openapi.openapi_definition import OpenApiDefinition, openapi_definition, openapi_definition_of

__all__ = ["OpenApiDefinition", "openapi_definition", "openapi_definition_of"]
