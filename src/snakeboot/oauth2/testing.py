"""The authorization server of a test: it signs the JWTs that the application of the test trusts."""

import time
from functools import cache
from typing import Final, override

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from snakeboot.configuration import OAuth2Properties
from snakeboot.oauth2.jwt_bearer_authentication import JwtSigningKeys

KEY_ID: Final = "snakeboot-test"
"""The `kid` of the key a test signs with."""

TOKEN_LIFESPAN_SECONDS: Final = 300
"""How long a token of the authorization server of a test is valid, unless the test says `exp` itself."""


class AuthorizationServer:
    """The authorization server of a test, in the place of Keycloak: it signs the tokens the application then trusts.

        @application_test
        def test_a_realm_role_of_keycloak_opens_the_endpoint(
            client: Autowired[RestClient], keycloak: Autowired[AuthorizationServer]
        ) -> None:
            headers = keycloak.signed_in("carol", realm_access={"roles": ["auctioneer"]})

    Where `signed_in_as` hands the application a principal, this signs a real JWT with a key of the test, with the
    issuer and the audience of `[oauth2]`: the application's own `JwtBearerAuthentication` checks it, and its own
    `roles_of` reads the roles from the claims, as it does in production. Any claim may be given, `exp` and `iss`
    included, to show what the application refuses.
    """

    def __init__(self, properties: OAuth2Properties) -> None:
        self._issuer = properties.issuer_uri
        self._audience = properties.audience
        self._key = _signing_key()

    def token(self, subject: str, **claims: object) -> str:
        """Returns a token of `subject` with `claims`, signed, issued now for `[oauth2]`'s audience."""
        now = int(time.time())
        payload = {
            "sub": subject,
            "iss": self._issuer,
            "aud": self._audience,
            "iat": now,
            "exp": now + TOKEN_LIFESPAN_SECONDS,
            **claims,
        }
        return jwt.encode(payload, self._key, algorithm="RS256", headers={"kid": KEY_ID})

    def signed_in(self, subject: str, **claims: object) -> dict[str, str]:
        """Returns the headers of a call with the token of `subject`: `{"Authorization": "Bearer ..."}`."""
        return {"Authorization": f"Bearer {self.token(subject, **claims)}"}

    def signing_keys(self) -> JwtSigningKeys:
        """Returns what verifies the server's tokens, in place of the issuer's key set."""
        public = jwt.algorithms.RSAAlgorithm.to_jwk(self._key.public_key(), as_dict=True)
        return _OneSigningKey(jwt.PyJWK({**public, "kid": KEY_ID, "alg": "RS256", "use": "sig"}))


class _OneSigningKey(JwtSigningKeys):
    """The public key of the authorization server of a test, whatever the token names."""

    def __init__(self, key: jwt.PyJWK) -> None:
        self._key = key

    @override
    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK:
        return self._key


@cache
def _signing_key() -> RSAPrivateKey:
    # One key per process: making one takes a while, and every test may share it.
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)
