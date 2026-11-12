"""A library of two bounded contexts, one module per role, as a hexagonal application has them: slices start parts."""

from snakeboot.component_scan import application_root
from snakeboot.openapi import openapi_definition


@openapi_definition(title="Library", version="1.0.0")
@application_root
class LibraryApplication:
    """The catalogue knows which books are on the shelf; loans lends them to members."""
