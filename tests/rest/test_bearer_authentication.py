"""A `BearerAuthentication` in the component scan is a component, whichever web framework checks the tokens."""

from typing import override

import wireup

from snakeboot.rest import BearerAuthentication
from tests.rest.secured import token_checker
from tests.rest.secured.token_checker import TokenChecker


def test_a_subclass_is_a_component_of_the_container() -> None:
    container = wireup.create_sync_container(injectables=[token_checker])

    assert isinstance(container.get(BearerAuthentication), TokenChecker)


def test_an_abstract_subclass_is_not_registered() -> None:
    class StillAbstract(BearerAuthentication):
        pass

    assert "__wireup_registration__" not in vars(StillAbstract)


def test_a_base_meant_to_be_extended_is_not_registered() -> None:
    class Base(BearerAuthentication, component=False):
        @override
        def authenticate(self, token: str) -> str | None:
            return token

    assert "__wireup_registration__" not in vars(Base)
