"""`signed_in_as` gives the headers of a call by a user with roles; only an application of a test accepts them."""

import pytest

from snakeboot.security import Principal
from snakeboot.testing import signed_in_as
from snakeboot.testing.signed_in_tokens import TOKEN_PREFIX, signed_in_principal


def test_the_token_carries_the_name_and_the_roles() -> None:
    headers = signed_in_as("carol", roles={"auctioneer", "bidder"})

    token = headers["Authorization"].removeprefix("Bearer ")

    assert token.startswith(TOKEN_PREFIX)
    assert signed_in_principal(token) == Principal("carol", frozenset({"auctioneer", "bidder"}))


def test_a_user_may_have_no_roles() -> None:
    token = signed_in_as("dave")["Authorization"].removeprefix("Bearer ")

    assert signed_in_principal(token) == Principal("dave")


@pytest.mark.parametrize(
    "token",
    ["wendy-token", f"{TOKEN_PREFIX}not base64!", f"{TOKEN_PREFIX}e30=", f"{TOKEN_PREFIX}WyJhIl0="],
    ids=["another kind", "garbled", "no name", "no object"],
)
def test_any_other_token_names_nobody(token: str) -> None:
    assert signed_in_principal(token) is None
