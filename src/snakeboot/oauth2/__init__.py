"""Technical library: accept the JWT access tokens of an OAuth2 authorization server, such as a Keycloak realm.

    # application.toml                          # an adapter in the component scan
    [oauth2]                                    class PlayerTokens(JwtBearerAuthentication):
    issuer_uri = "http://localhost:8180/realms/kareldegames"     \"\"\"Keycloak's tokens for players.\"\"\"
    jwks_uri = "http://keycloak:8080/realms/kareldegames/protocol/openid-connect/certs"
    audience = "tictactoe"

Like `spring-boot-starter-oauth2-resource-server`: every endpoint then needs a valid token, and the `name` of an
endpoint's `Principal` is its subject. It knows the REST library, the configuration and PyJWT, but no web framework
(extra: snakeboot[oauth2]).
"""

from snakeboot.oauth2.jwt_bearer_authentication import JwtBearerAuthentication, JwtSigningKeys

__all__ = ["JwtBearerAuthentication", "JwtSigningKeys"]
