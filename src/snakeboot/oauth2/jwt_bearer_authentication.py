import logging
from typing import Final, override

import jwt

from snakeboot.configuration import OAuth2Properties
from snakeboot.rest import BearerAuthentication

logger = logging.getLogger(__name__)

REQUIRED_CLAIMS: Final = ("exp", "iss", "aud", "sub")
"""A token without one of these claims is refused, whatever its signature."""

KEY_LIFESPAN_SECONDS: Final = 300
"""How long the issuer's public keys are kept before they are fetched again (a key rotation takes at most this)."""


class JwtBearerAuthentication(BearerAuthentication):
    """Accepts the signed JWT access tokens of one authorization server, like Spring's oauth2 resource server.

    A token is valid when the issuer's public key (fetched from `jwks_uri` and cached) verifies its signature, its
    `iss` is `issuer_uri`, its `aud` holds `audience` and it has not expired. The principal is its `sub`. Every other
    token, and every token while the keys cannot be fetched, is answered with 401.

    An application turns it on with one adapter in its component scan and the table `[oauth2]` in application.toml:

        class PlayerTokens(JwtBearerAuthentication):
            \"\"\"The access tokens that Keycloak gives the platform's players.\"\"\"
    """

    def __init__(self, properties: OAuth2Properties) -> None:
        self._issuer = properties.issuer_uri
        self._audience = properties.audience
        self._signing_keys = jwt.PyJWKClient(properties.jwks_uri, cache_keys=True, lifespan=KEY_LIFESPAN_SECONDS)

    @override
    def authenticate(self, token: str) -> str | None:
        try:
            signing_key = self._signing_keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=[signing_key.algorithm_name],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": list(REQUIRED_CLAIMS)},
            )
        except jwt.PyJWTError as error:
            logger.info("A bearer token was refused: %s", error)
            return None
        return str(claims["sub"])
