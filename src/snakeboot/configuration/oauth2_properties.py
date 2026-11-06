from snakeboot.configuration.configuration_properties import configuration_properties
from snakeboot.configuration.section import Section


@configuration_properties("oauth2")
class OAuth2Properties(Section):
    """The section `[oauth2]`: whose access tokens the API accepts, like `spring.security.oauth2.resourceserver.jwt.*`.

    `issuer_uri` is the issuer the tokens name (for Keycloak, the realm's URL as the browser sees it), `jwks_uri` where
    the service fetches the issuer's public keys (in a container often another host name than the issuer), and
    `audience` the client the tokens must be meant for.

        [oauth2]
        issuer_uri = "http://localhost:8180/realms/kareldegames"
        jwks_uri = "http://keycloak:8080/realms/kareldegames/protocol/openid-connect/certs"
        audience = "tictactoe"
    """

    issuer_uri: str
    jwks_uri: str
    audience: str
