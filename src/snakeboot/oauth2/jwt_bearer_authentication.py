import logging
from collections.abc import Mapping
from typing import Any, Final, override

import jwt

from snakeboot.configuration import OAuth2Properties
from snakeboot.rest import BearerAuthentication
from snakeboot.security import Principal

logger = logging.getLogger(__name__)

REQUIRED_CLAIMS: Final = ("exp", "iss", "aud", "sub")
"""A token without one of these claims is refused, whatever its signature."""

KEY_LIFESPAN_SECONDS: Final = 300
"""How long the issuer's public keys are kept before they are fetched again (a key rotation takes at most this)."""


class JwtBearerAuthentication(BearerAuthentication, component=False):
    """Accepts the signed JWT access tokens of one authorization server, like Spring's oauth2 resource server.

    A token is valid when the issuer's public key (fetched from `jwks_uri` and cached) verifies its signature, its
    `iss` is `issuer_uri`, its `aud` holds `audience` and it has not expired. The principal is its `sub`, with the roles
    `roles_of` finds in its claims. Every other token, and every token while the keys cannot be fetched, is answered
    with 401.

    It is not a component itself: an application turns it on with one subclass in its component scan and the table
    `[oauth2]` in application.toml:

        class PlayerTokens(JwtBearerAuthentication):
            \"\"\"The access tokens that Keycloak gives the platform's players.\"\"\"
    """

    def __init__(self, properties: OAuth2Properties) -> None:
        self._issuer = properties.issuer_uri
        self._audience = properties.audience
        self._signing_keys = jwt.PyJWKClient(properties.jwks_uri, cache_keys=True, lifespan=KEY_LIFESPAN_SECONDS)

    @override
    def authenticate(self, token: str) -> Principal | None:
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
        return Principal(str(claims["sub"]), roles=self.roles_of(claims))

    def roles_of(self, claims: Mapping[str, Any]) -> frozenset[str]:
        """Returns the roles a valid token grants, like Spring's `JwtGrantedAuthoritiesConverter`.

        Keycloak's realm roles (`realm_access.roles`), its client roles for the audience
        (`resource_access.<audience>.roles`) and a plain `roles` claim, as Microsoft Entra ID writes it. Override it
        for an authorization server that puts them elsewhere.
        """
        client_roles = _mapping(_mapping(claims.get("resource_access")).get(self._audience))
        return frozenset(
            role
            for listed in (
                _mapping(claims.get("realm_access")).get("roles"),
                client_roles.get("roles"),
                claims.get("roles"),
            )
            if isinstance(listed, list)
            for role in listed
            if isinstance(role, str)
        )


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
