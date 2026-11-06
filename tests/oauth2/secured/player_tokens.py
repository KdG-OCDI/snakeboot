from snakeboot.oauth2 import JwtBearerAuthentication


class PlayerTokens(JwtBearerAuthentication):
    """Keycloak's tokens for players: what an application writes, importing the base into its module."""
