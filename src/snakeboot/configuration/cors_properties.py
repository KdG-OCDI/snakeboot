from typing import Self

from pydantic import model_validator

from snakeboot.configuration.configuration_properties import configuration_properties
from snakeboot.configuration.section import Section


@configuration_properties("cors")
class CorsProperties(Section):
    """The optional section `[cors]`: which pages of other origins may call the REST API, like Spring's `CorsRegistry`.

    A browser refuses a page of `https://games.example.com` the answers of an API on `https://api.example.com`, unless
    the API names that origin. Without the section, the API names none: a page of the same origin, or a proxy in
    front of both, needs nothing. `*` allows any origin, but not together with credentials (cookies), as in Spring.

        [cors]
        allowed_origins = ["https://games.example.com"]
        allowed_methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]
        allowed_headers = ["Authorization", "Content-Type"]
        allow_credentials = false
    """

    allowed_origins: tuple[str, ...]
    allowed_methods: tuple[str, ...]
    allowed_headers: tuple[str, ...]
    allow_credentials: bool

    @model_validator(mode="after")
    def _refuse_any_origin_with_credentials(self) -> Self:
        if self.allow_credentials and "*" in self.allowed_origins:
            raise ValueError("allow_credentials needs the origins themselves: allowed_origins cannot hold '*'.")
        return self
