"""`Principal` lives in `snakeboot.security`; the REST library hands it to endpoints under its old name too."""

from snakeboot.security.principal import Principal

__all__ = ["Principal"]
