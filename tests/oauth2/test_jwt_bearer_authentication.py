"""`JwtBearerAuthentication` accepts the signed tokens of one issuer for one audience, and nothing else."""

import json
import time
from typing import Any

import jwt
import pytest
import wireup
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from snakeboot.configuration import OAuth2Properties
from snakeboot.oauth2 import JwtBearerAuthentication
from snakeboot.rest import BearerAuthentication
from tests.oauth2.secured import player_tokens
from tests.oauth2.secured.player_tokens import PlayerTokens

ISSUER = "http://localhost:8180/realms/test"
AUDIENCE = "greeting"
KEY_ID = "test-key"


def new_key() -> RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


ISSUER_KEY = new_key()


def key_set_of(key: RSAPrivateKey) -> dict[str, Any]:
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    return {"keys": [{**public, "kid": KEY_ID, "alg": "RS256", "use": "sig"}]}


def token(key: RSAPrivateKey = ISSUER_KEY, **claims: Any) -> str:
    now = int(time.time())
    payload = {"sub": "ann", "iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 60, **claims}
    return jwt.encode(
        {k: v for k, v in payload.items() if v is not None}, key, algorithm="RS256", headers={"kid": KEY_ID}
    )


@pytest.fixture
def authentication(monkeypatch: pytest.MonkeyPatch) -> JwtBearerAuthentication:
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda _client: key_set_of(ISSUER_KEY))
    properties = OAuth2Properties(issuer_uri=ISSUER, jwks_uri="http://keycloak/certs", audience=AUDIENCE)
    return JwtBearerAuthentication(properties)


def test_a_valid_token_gives_its_subject(authentication: JwtBearerAuthentication) -> None:
    assert authentication.authenticate(token()) == "ann"


def test_a_subclass_is_a_component_and_the_base_is_not() -> None:
    assert "__wireup_registration__" in vars(PlayerTokens)
    assert "__wireup_registration__" not in vars(JwtBearerAuthentication)


@pytest.mark.parametrize(
    "claims",
    [
        pytest.param({"aud": "another-client"}, id="another audience"),
        pytest.param({"iss": "http://evil.example/realms/test"}, id="another issuer"),
        pytest.param({"exp": int(time.time()) - 120}, id="expired"),
        pytest.param({"exp": None}, id="without expiry"),
        pytest.param({"sub": None}, id="without subject"),
    ],
)
def test_a_token_with_wrong_claims_is_refused(authentication: JwtBearerAuthentication, claims: dict[str, Any]) -> None:
    assert authentication.authenticate(token(**claims)) is None


def test_a_token_signed_by_another_key_is_refused(authentication: JwtBearerAuthentication) -> None:
    assert authentication.authenticate(token(new_key())) is None


def test_a_token_that_is_no_jwt_is_refused(authentication: JwtBearerAuthentication) -> None:
    assert authentication.authenticate("not-a-token") is None


def test_while_the_keys_cannot_be_fetched_every_token_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    def unreachable(_client: jwt.PyJWKClient) -> dict[str, Any]:
        raise jwt.PyJWKClientConnectionError("connection refused")

    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", unreachable)
    properties = OAuth2Properties(issuer_uri=ISSUER, jwks_uri="http://keycloak/certs", audience=AUDIENCE)

    assert JwtBearerAuthentication(properties).authenticate(token()) is None


def test_it_is_a_bearer_authentication() -> None:
    assert issubclass(JwtBearerAuthentication, BearerAuthentication)


def test_a_module_that_extends_it_gives_the_container_one_bearer_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda _client: key_set_of(ISSUER_KEY))
    properties = OAuth2Properties(issuer_uri=ISSUER, jwks_uri="http://keycloak/certs", audience=AUDIENCE)
    container = wireup.create_sync_container(
        injectables=[player_tokens, wireup.instance(properties, as_type=OAuth2Properties)]
    )

    authentication = container.get(BearerAuthentication)

    assert isinstance(authentication, PlayerTokens)
    assert authentication.authenticate(token()) == "ann"
