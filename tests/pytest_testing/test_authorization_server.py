"""The `AuthorizationServer` of a test signs real JWTs, which the application's own `JwtBearerAuthentication` checks.

Where `signed_in_as` hands the application a principal, these tokens go through its signature check, its issuer and
audience, and its own `roles_of`: the mapping of Keycloak's roles is tested too.
"""

import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from snakeboot.boot.testing import RestClient
from snakeboot.configuration import OAuth2Properties
from snakeboot.oauth2 import JwtBearerAuthentication
from snakeboot.oauth2.testing import AuthorizationServer
from snakeboot.security import Principal
from snakeboot.testing import Autowired, application_test, signed_in_as
from tests.pytest_testing.realm.vault import RealmApplication

realm_test = application_test(application=RealmApplication)


@realm_test
class TestTheTokensOfTheAuthorizationServer:
    client: Autowired[RestClient]
    keycloak: Autowired[AuthorizationServer]

    def test_a_realm_role_reaches_the_endpoint_through_the_applications_own_mapping(self) -> None:
        headers = self.keycloak.signed_in("kim", realm_access={"roles": ["keeper", "offline_access"]})

        response = self.client.get("/api/vault", headers=headers)

        assert (response.status_code, response.json()) == (200, {"name": "kim", "roles": ["keeper", "offline_access"]})

    def test_a_client_role_of_the_audience_counts_too(self) -> None:
        headers = self.keycloak.signed_in("kim", resource_access={"vault-api": {"roles": ["keeper"]}})

        assert self.client.get("/api/vault", headers=headers).status_code == 200

    def test_a_token_without_the_role_is_forbidden(self) -> None:
        headers = self.keycloak.signed_in("vic", realm_access={"roles": ["visitor"]})

        assert self.client.get("/api/vault", headers=headers).status_code == 403

    def test_an_expired_token_is_refused(self) -> None:
        headers = self.keycloak.signed_in("kim", realm_access={"roles": ["keeper"]}, exp=int(time.time()) - 60)

        assert self.client.get("/api/vault", headers=headers).status_code == 401

    def test_a_token_of_another_issuer_is_refused(self) -> None:
        headers = self.keycloak.signed_in("kim", realm_access={"roles": ["keeper"]}, iss="http://elsewhere/realms/x")

        assert self.client.get("/api/vault", headers=headers).status_code == 401

    def test_signed_in_as_still_counts_beside_them(self) -> None:
        response = self.client.get("/api/vault", headers=signed_in_as("kim", roles={"keeper"}))

        assert response.status_code == 200


@realm_test
def test_a_token_signed_by_another_key_is_refused(client: Autowired[RestClient]) -> None:
    stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = {"sub": "kim", "iss": "http://localhost:8180/realms/vault", "aud": "vault-api", "exp": time.time() + 60}
    forged = jwt.encode({**claims, "realm_access": {"roles": ["keeper"]}}, stranger, algorithm="RS256")

    assert client.get("/api/vault", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_a_jwt_bearer_authentication_trusts_the_signing_keys_it_is_given() -> None:
    properties = OAuth2Properties(issuer_uri="http://issuer", jwks_uri="http://issuer/certs", audience="api")
    issuer = AuthorizationServer(properties)
    authentication = JwtBearerAuthentication(properties, signing_keys=issuer.signing_keys())

    principal = authentication.authenticate(issuer.token("ann", roles=["reader"]))

    assert principal == Principal("ann", frozenset({"reader"}))
